from datetime import timedelta

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: timedelta = timedelta(minutes=60)
    POSTGRESQL_USER: str
    POSTGRESQL_PASSWORD: str
    POSTGRESQL_SERVER: str
    POSTGRESQL_PORT: int = 5432
    POSTGRESQL_DATABASE: str

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.POSTGRESQL_USER}:{self.POSTGRESQL_PASSWORD}@]{self.POSTGRESQL_SERVER}:{self.POSTGRESQL_PORT}/{self.POSTGRESQL_DATABASE}"

    INITAL_ADMIN_NAME: str
    INITAL_ADMIN_PASSWORD: str
    INITAL_NORMAL_USER_PASSWORD: str

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()  # type: ignore
