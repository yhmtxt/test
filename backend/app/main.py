from uuid import UUID
from typing import Annotated, AsyncGenerator
from contextlib import asynccontextmanager

from pydantic import BaseModel
from fastapi import FastAPI, Depends, Body, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import select

from .config import settings
from .models import Group, User, Classroom, Role, UserPublic, ClassroomCreate
from .dependences import (
    create_all_db_and_tables,
    SessionDep,
    get_admin,
)
from .utils import verify_password, get_password_hash, create_access_token


class Token(BaseModel):
    access_token: str
    token_type: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    create_all_db_and_tables()
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


@app.post("/classrooms", status_code=201, dependencies=[Depends(get_admin)])
def create_classroom(
    session: SessionDep, classroom_create: ClassroomCreate
) -> Classroom:
    classroom = Classroom(name=classroom_create.name)
    for student_name in classroom_create.student_names:
        student = User(
            name=student_name,
            hashed_password=get_password_hash(settings.INITAL_NORMAL_USER_PASSWORD),
            role=Role.STUDENT,
            classroom_id=classroom.id,
            classroom=classroom,
        )
        classroom.users.append(student)
    session.add(classroom)
    session.commit()
    session.refresh(classroom)
    return classroom


@app.delete(
    "/classrooms/{classroom_id}", status_code=204, dependencies=[Depends(get_admin)]
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
    access_token = create_access_token({"sub": user.id, "name": user.name})
    return Token(access_token=access_token, token_type="bearer")
