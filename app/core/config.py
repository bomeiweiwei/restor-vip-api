from typing import Optional
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

    EMBEDDING_PROVIDER: str = "azure"

    AZURE_OPENAI_EMBEDDING_MODEL: str
    GEMINI_EMBEDDING_MODEL: Optional[str] = None

    AI_PROVIDER: str = "azure"

    AZURE_OPENAI_BASE_URL: str
    AZURE_OPENAI_API_KEY: str
    AZURE_OPENAI_DEPLOYMENT_NAME: str

    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL_NAME: Optional[str] = None

    GOOGLE_CREDENTIALS_JSON: Optional[str] = None
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    GOOGLE_CLOUD_PROJECT: Optional[str] = None
    GOOGLE_CLOUD_LOCATION: Optional[str] = None

    LMSTUDIO_BASE_URL: Optional[str] = None
    LMSTUDIO_API_KEY: Optional[str] = None
    LMSTUDIO_MODEL_NAME: Optional[str] = None

    OPEN_WEATHER_MAP_API_KEY: str | None = None
    WEATHER_API_BASE: str = "https://api.openweathermap.org/data/2.5" 

    CWA_API_KEY: str
    CWA_DATASET_ID: str = "F-D0047-001"
    CWA_LOCATION_NAME: str = "五結鄉"
    
    TDX_CLIENT_ID: str
    TDX_CLIENT_SECRET: str
    TDX_API_BASE: str = "https://tdx.transportdata.tw/api/basic/v2"
    TDX_BUS_CITY: str = "YilanCounty"

    QDRANT_URL: str
    QDRANT_API_KEY: str
    QDRANT_COLLECTION_NAME: str
    QDRANT_TIMEOUT_SECONDS: str

    AZURE_TRANSLATOR_KEY: str
    AZURE_TRANSLATOR_ENDPOINT: str
    AZURE_TRANSLATOR_REGION: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()