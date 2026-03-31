from uuid import UUID
from typing import Annotated, AsyncGenerator
from contextlib import asynccontextmanager

from pydantic import BaseModel
from fastapi import (
    FastAPI,
    Depends,
    Body,
    HTTPException,
    WebSocket,
    Query,
    WebSocketDisconnect,
)
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import select

from .config import settings
from .models import (
    Group,
    User,
    Classroom,
    UserPublic,
    ClassroomCreate,
    AdminInfo,
    StudentInfo,
)
from .dependences import (
    create_all_db_and_tables,
    get_session,
    SessionDep,
    get_current_user,
    get_current_admin,
)
from .utils import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_user_from_token,
)


class WebsocketBroadcastManagerByGroup:
    def __init__(self) -> None:
        self.connection_pool: dict[str, set[WebSocket]] = {}

    def connect(self, group_id: str, connection: WebSocket) -> None:
        if group_id in self.connection_pool:
            self.connection_pool[group_id].add(connection)
        else:
            self.connection_pool[group_id] = {connection}

    def disconnect(self, connection: WebSocket) -> None:
        for group_id in self.connection_pool:
            if connection in self.connection_pool[group_id]:
                self.connection_pool[group_id].remove(connection)
                if not self.connection_pool[group_id]:
                    del self.connection_pool[group_id]

    async def broadcast_text(self, group_id: str, text: str) -> None:
        for connection in self.connection_pool[group_id]:
            await connection.send_text(text)


code_broadcast_manager = WebsocketBroadcastManagerByGroup()


class Token(BaseModel):
    access_token: str
    token_type: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    create_all_db_and_tables()
    with get_session() as session:
        admin = session.exec(
            select(User).where(User.name == settings.INITAL_ADMIN_NAME)
        ).first()
        if admin is None:
            info = AdminInfo()
            admin = User(
                name=settings.INITAL_ADMIN_NAME,
                hashed_password=get_password_hash(settings.INITAL_ADMIN_PASSWORD),
                admin_info=info,
            )
            session.add(admin)
            session.commit()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/classrooms")
def get_all_classrooms(session: SessionDep) -> list[Classroom]:
    classrooms = session.exec(select(Classroom)).all()
    return list(classrooms)


@app.get("/classrooms/{classroom_id}")
def get_classroom(session: SessionDep, classroom_id: UUID) -> Classroom:
    classroom = session.get(Classroom, classroom_id)
    if classroom is None:
        raise HTTPException(404, "教室不存在")
    return classroom


@app.post("/classrooms", status_code=201, dependencies=[Depends(get_current_admin)])
def create_classroom(
    session: SessionDep, classroom_create: ClassroomCreate
) -> Classroom:
    classroom = Classroom(name=classroom_create.name)
    for student_name in classroom_create.student_names:
        student = User(
            name=student_name,
            hashed_password=get_password_hash(settings.INITAL_NORMAL_USER_PASSWORD),
        )
        info = StudentInfo(classroom_id=classroom.id, classroom=classroom, user=student)
        classroom.students.append(info)
    session.add(classroom)
    session.commit()
    session.refresh(classroom)
    return classroom


@app.delete(
    "/classrooms/{classroom_id}",
    status_code=204,
    dependencies=[Depends(get_current_admin)],
)
def delete_classrooms(
    session: SessionDep, classroom: Annotated[Classroom, Depends(get_classroom)]
) -> None:
    session.delete(classroom)
    session.commit()


@app.get("/groups")
def get_all_groups(session: SessionDep) -> list[Group]:
    groups = session.exec(select(Group)).all()
    return list(groups)


@app.get("/groups/{group_id}")
def get_group(session: SessionDep, group_id: UUID) -> Group:
    group = session.get(Group, group_id)
    if group is None:
        raise HTTPException(404, detail="小组不存在")
    return group


@app.put("/groups/{group_id}/code", status_code=204)
def update_code_for_group(
    session: SessionDep,
    group: Annotated[Group, Depends(get_group)],
    user: Annotated[User, Depends(get_current_user)],
    code: Annotated[str, Body()],
) -> None:
    if group.leader is not user:
        raise HTTPException(403, detail="只有组长能编辑代码")
    group.code = code
    session.add(group)
    session.commit()


@app.post("/groups")
def create_group(session: SessionDep, name: Annotated[str, Body()]) -> Group:
    group = Group(name=name)
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


@app.get("/users", response_model=UserPublic)
def get_all_users(session: SessionDep) -> list[User]:
    users = session.exec(select(User)).all()
    return list(users)


@app.get("/users/{user_id}", response_model=UserPublic)
def get_user(session: SessionDep, user_id: UUID) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(404, detail="用户不存在")
    return user


@app.post("/log_in")
def log_in(
    session: SessionDep, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> Token:
    user = session.exec(select(User).where(User.name == form_data.username)).first()
    if user is None:
        raise HTTPException(404, detail="用户不存在")
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(401, "密码不正确")
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token({"sub": str(user.id), "name": user.name})
    return Token(access_token=access_token, token_type="bearer")


@app.websocket("/ws/code")
async def sync_code(
    session: SessionDep, websocket: WebSocket, token: Annotated[str, Query()]
) -> None:
    try:
        user = get_user_from_token(session, token)
    except ValueError:
        await websocket.close(code=1008, reason="Invalid token")
        return

    if user.student_info is None:
        await websocket.close(code=1008, reason="权限不足")
        return

    group = user.student_info.group

    if group is None:
        await websocket.close(code=1008, reason="没有小组")
        return

    await websocket.accept()

    code_broadcast_manager.connect(str(group.id), websocket)
    try:
        while True:
            code = await websocket.receive_text()
            if not user.student_info.leaded_group:
                await websocket.send_json({"error": "只有组长有编辑权限"})
            group.code = code
            session.add(group)
            session.commit()
            await websocket.send_text(code)
    except WebSocketDisconnect:
        code_broadcast_manager.disconnect(websocket)
