from datetime import datetime, timedelta, timezone

import jwt
from sqlmodel import Session
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

from .config import settings
from .models import User

password_hash = PasswordHash.recommended()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


def create_access_token(
    data: dict, expires_delta: timedelta = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    token = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return token


def get_user_from_token(session: Session, token: str) -> User:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise ValueError
    except InvalidTokenError:
        raise ValueError
    user = session.get(User, user_id)
    if user is None:
        raise ValueError
    return user
