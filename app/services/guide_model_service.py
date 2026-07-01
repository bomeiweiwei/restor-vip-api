from google import genai
from openai import OpenAI

from app.core.config import settings


def get_guide_model(provider: str | None = None):
    """
    專屬導遊 LLM client factory。

    GUIDE_MODEL_PROVIDER=gemini -> Gemini
    GUIDE_MODEL_PROVIDER=azure  -> Azure OpenAI
    """
    provider = (provider or settings.GUIDE_MODEL_PROVIDER).lower().strip()

    if provider == "gemini":
        api_key = settings.GUIDE_GEMINI_API_KEY or settings.GEMINI_API_KEY

        if not api_key:
            raise ValueError(
                "找不到 GUIDE_GEMINI_API_KEY 或 GEMINI_API_KEY，請先在 .env 設定。"
            )

        return genai.Client(api_key=api_key)

    if provider == "azure":
        base_url = settings.AZURE_OPENAI_BASE_URL.rstrip("/")

        if not base_url.endswith("/openai/v1"):
            base_url = f"{base_url}/openai/v1"

        return OpenAI(
            base_url=f"{base_url}/",
            api_key=settings.AZURE_OPENAI_API_KEY,
        )

    raise ValueError(f"目前不支援的 GUIDE_MODEL_PROVIDER：{provider}")