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

    AZURE_SPEECH_KEY: str
    AZURE_SPEECH_REGION: str

    EMBEDDING_PROVIDER: str

    AZURE_OPENAI_EMBEDDING_MODEL: str
    GEMINI_EMBEDDING_MODEL: str

    AI_PROVIDER: str

    AZURE_OPENAI_BASE_URL: str
    AZURE_OPENAI_API_KEY: str
    AZURE_OPENAI_DEPLOYMENT_NAME: str

    GEMINI_API_KEY: str
    GEMINI_MODEL_NAME: str

    GOOGLE_APPLICATION_CREDENTIALS: str
    GOOGLE_CLOUD_PROJECT: str
    GOOGLE_CLOUD_LOCATION: str

    LMSTUDIO_BASE_URL: str
    LMSTUDIO_API_KEY: str
    LMSTUDIO_MODEL_NAME: str

    OPEN_WEATHER_MAP_API_KEY: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()