import asyncio
from uuid import UUID, uuid4
from typing import Annotated, AsyncGenerator, Any
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
    UserPublic,
    AdminInfo,
    StudentInfo,
)
from .dependences import (
    create_all_db_and_tables,
    get_session,
    SessionDep,
    get_current_user,
)
from .utils import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_user_from_token,
)
from .robot_apis import InitResponse, API, CommandRequest, CommandResponse


class Robot:
    def __init__(self, connection: WebSocket, id: UUID, name: str, apis: list[API]):
        self.connection = connection
        self.id = id
        self.name = name
        self.apis = apis
        self.pending_commands: dict[UUID, asyncio.Future] = {}

    def set_future(self, command_id: UUID, future: asyncio.Future):
        self.pending_commands[command_id] = future

    def get_future(self, command_id: UUID) -> asyncio.Future | None:
        return self.pending_commands.get(command_id)

    def remove_future(self, command_id: UUID):
        if command_id in self.pending_commands:
            del self.pending_commands[command_id]

    def cancel_all_pending(self):
        for future in self.pending_commands.values():
            if not future.done():
                future.set_exception(ConnectionError("机器人已断开"))
        self.pending_commands.clear()

    # def __getattr__(self, name):
    #     async def send_command(*args):
    #         await self.connection.send_json(CommandRequest(id=uuid4(), name=name, parameter=list(args)).model_dump())
    #     if name in [api.name for api in self.apis]:
    #         return send_command

class RobotConnectionManager:
    def __init__(self):
        self.robots: dict[UUID, Robot] = {}

    def register(self, robot: Robot):
        self.robots[robot.id] = robot

    def unregister(self, robot_id: UUID):
        robot = self.robots.pop(robot_id, None)
        if robot:
            robot.cancel_all_pending()
            # 可选：关闭连接
            # asyncio.create_task(robot.connection.close(code=1000))

    def get(self, robot_id: UUID) -> Robot | None:
        return self.robots.get(robot_id)

    def list_robots(self) -> list[dict]:
        return [
            {
                "robot_id": r.id,
                "robot_name": r.name,
                "apis": [api.model_dump() for api in r.apis]
            }
            for r in self.robots.values()
        ]

robot_manager = RobotConnectionManager()

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


@app.post("/groups")
def create_group(
    session: SessionDep,
    user: Annotated[User, Depends(get_current_user)],
    name: Annotated[str, Body()],
    student_names: Annotated[list[str], Body()],
) -> Group:
    if user.admin_info is None or user.teacher_info is None:
        raise HTTPException(403, detail="权限不足")

    group = Group(name=name)
    for student_name in student_names:
        stu = User(
            name=student_name,
            hashed_password=get_password_hash(settings.INITAL_NORMAL_USER_PASSWORD),
        )
        info = StudentInfo(user=stu)
        group.students.append(info)
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


@app.websocket("/web/robot")
async def connect_robot(websocket: WebSocket, init: Annotated[InitResponse, Query()]) -> None:
    await websocket.accept()

    robot = Robot(websocket, init.robot_id, init.robot_name, init.apis)
    while True:
        msg = await websocket.receive_json()
        response = CommandResponse(**msg)
        future = robot.get_future(response.id)
        if future and not future.done():
            future.set_result(response)
        else:
            pass

# @app.post("/robot/command/{robot_id}")
# async def send_command(
#     robot_id: UUID,
#     command_name: str = Body(..., embed=True),
#     parameters: list[Any] = Body(..., embed=True)
# ) -> CommandResponse:
#     robot = robot_manager.get(robot_id)
#     if not robot:
#         raise HTTPException(404, detail="机器人未连接")

#     command_id = uuid4()
#     future = asyncio.Future()
#     robot.set_future(command_id, future)

#     try:
#         # 发送命令
#         request = CommandRequest(
#             id=command_id,
#             name=command_name,
#             parameter=parameters
#         )
#         await robot.connection.send_json(request.model_dump())

#         # 等待响应（超时 10 秒）
#         response = await asyncio.wait_for(future, timeout=10.0)
#         return response
#     except asyncio.TimeoutError:
#         raise HTTPException(408, detail="命令执行超时")
#     finally:
#         robot.remove_future(command_id)