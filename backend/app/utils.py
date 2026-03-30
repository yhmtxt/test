from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from .config import settings

password_hash = PasswordHash.recommended()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


def create_access_token(
    data: dict, expires_delta: timedelta = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    token = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return token
