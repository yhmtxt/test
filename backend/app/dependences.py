from typing import Annotated
from contextlib import contextmanager

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import SQLModel, create_engine, Session

from .config import settings
from .models import User
from .utils import get_user_from_token

engine = create_engine(settings.DATABASE_URL)


def create_all_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def __get_session():
    with Session(engine) as session:
        yield session


get_session = contextmanager(__get_session)

SessionDep = Annotated[Session, Depends(__get_session)]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/log_in")


def get_current_user(
    session: SessionDep, token: Annotated[str, Depends(oauth2_scheme)]
) -> User:
    try:
        user = get_user_from_token(session, token)
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_admin:
        raise HTTPException(403, "权限不足")
    return user
