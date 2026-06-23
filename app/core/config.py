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

    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    GOOGLE_CLOUD_PROJECT: Optional[str] = None
    GOOGLE_CLOUD_LOCATION: Optional[str] = None

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


    # guide 專屬導遊：保留guid專案原本vb路徑 (data/) 架構
    GUIDE_PROJECT_ROOT: str = "."
    GUIDE_SOURCE_DIR: str = "./data/raw/RAG知識庫"
    GUIDE_PROCESSED_DIR: str = "./data/processed"
    GUIDE_VECTOR_DB_DIR: str = "./data/vector_db/gemini_embedding_2"
    GUIDE_VECTOR_INDEX_FILE: str = "resort_knowledge.faiss"
    GUIDE_VECTOR_METADATA_FILE: str = "resort_knowledge.pkl"
    GUIDE_VECTOR_MANIFEST_FILE: str = "vector_manifest.json"
    GUIDE_CONVERTED_IMAGE_DIR: str = "./data/processed/converted_images"
    GUIDE_UPLOAD_DIR: str = "./uploads/guide"

    GUIDE_EMBEDDING_PROVIDER: str = "gemini"
    GUIDE_MODEL_PROVIDER: str = "gemini"
    GUIDE_GEMINI_API_KEY: Optional[str] = None
    GUIDE_GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-2"
    GUIDE_EMBEDDING_DIM: int = 3072
    GUIDE_GEMINI_GENERATION_MODEL: str = "gemini-2.5-flash-lite"

    GUIDE_TOP_K: int =8   # 最後拿來判斷景點與回答的資料數量，取前 8 筆相似結果
    GUIDE_FETCH_K: int = 80    # FAISS 先找出相似度最高的 80 筆，再從這 80 筆裡面取前 8 筆來生成回答
    GUIDE_SCORE_THRESHOLD: float = 0.65  # 最低信心門檻
    GUIDE_ENABLE_TTS: bool = False  # 是否啟用文字轉語音



    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()