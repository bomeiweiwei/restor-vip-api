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

    GOOGLE_CREDENTIALS_JSON: str
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    GOOGLE_CLOUD_PROJECT: str
    GOOGLE_CLOUD_LOCATION: str

    LMSTUDIO_BASE_URL: Optional[str] = None
    LMSTUDIO_API_KEY: Optional[str] = None
    LMSTUDIO_MODEL_NAME: Optional[str] = None

    OPEN_WEATHER_MAP_API_KEY: str

    QDRANT_URL: str
    QDRANT_API_KEY: str
    QDRANT_COLLECTION_NAME: str
    QDRANT_TIMEOUT_SECONDS: str

    AZURE_TRANSLATOR_KEY: str
    AZURE_TRANSLATOR_ENDPOINT: str
    AZURE_TRANSLATOR_REGION: str


    GUIDE_EMBEDDING_PROVIDER: str = "gemini"
    GUIDE_MODEL_PROVIDER: str = "gemini"
    GUIDE_GEMINI_API_KEY: Optional[str] = None
    GUIDE_GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-2"
    GUIDE_EMBEDDING_DIM: int = 3072
    GUIDE_GEMINI_GENERATION_MODEL: str = "gemini-2.5-flash-lite"
   

    # =========================
    # Guide vector DB backend
    # 專屬導遊向量資料庫來源：qdrant / faiss
    # =========================
    GUIDE_VECTOR_DB_BACKEND: str = "qdrant"

    # =========================
    # Guide Qdrant Cloud
    # 專屬導遊專用，避免和正式後端其他 Qdrant 設定混用。
    # =========================
    GUIDE_QDRANT_URL: str = ""
    GUIDE_QDRANT_API_KEY: str = ""
    GUIDE_QDRANT_COLLECTION_NAME: str = "resort_guide"
    GUIDE_QDRANT_TIMEOUT_SECONDS: int = 180


    # =========================
    # Azure Blob Storage for Guide data
    # Azure Blob 保存 Guide 原始 data、圖片、PDF 等資料。
    # =========================
    AZURE_STORAGE_AUTH_MODE: str = "connection_string"
    AZURE_STORAGE_ACCOUNT_NAME: str = ""
    AZURE_STORAGE_CONTAINER_NAME: str = ""
    AZURE_STORAGE_CONNECTION_STRING: str = ""

    ASSET_BASE_URL: str = ""

    TTS_PROVIDER: str = "gemini"

    AZURE_OPENAI_TTS_ENDPOINT: str
    AZURE_OPENAI_TTS_KEY: str
    AZURE_OPENAI_TTS_VERSION: str = "2025-03-01-preview"
    AZURE_OPENAI_TTS_DEPLOYMENT: str = "gpt-4o-mini-tts"
    AZURE_OPENAI_TTS_VOICE: str = "nova"

    GEMINI_TTS_MODEL: str = "gemini-2.5-flash-preview-tts"
    GEMINI_TTS_VOICE: str = "Kore"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()