from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Resort VIP API"

    DB_SERVER: str
    DB_DATABASE: str
    DB_USERNAME: str
    DB_PASSWORD: str
    DB_DRIVER: str = "ODBC Driver 18 for SQL Server"

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480

    FRONTEND_ORIGIN: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()