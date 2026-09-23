import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Computer Fleet Maintenance Scheduler (CFMS)"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "cfms-dev-secret-key-change-in-production-1234567890")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://cfms_user:cfms_password@localhost:5432/cfms_db")
    DEFAULT_LOCALE: str = "ru"

    class Config:
        env_file = ".env"


settings = Settings()
