from google import genai

from app.core.config import settings


def get_guide_model(provider: str | None = None):
    """
    專屬導遊的 Gemini API client。

    注意：這裡使用 Google AI Studio API Key 方式，
    不覆蓋正式後端 app/ai/factory.py，避免影響既有功能。
    """
    provider = (provider or settings.GUIDE_MODEL_PROVIDER).lower().strip()

    if provider == "gemini":
        api_key = settings.GUIDE_GEMINI_API_KEY or settings.GEMINI_API_KEY

        if not api_key:
            raise ValueError(
                "找不到 GUIDE_GEMINI_API_KEY 或 GEMINI_API_KEY，請先在 .env 設定。"
            )

        return genai.Client(api_key=api_key)

    raise ValueError(f"目前不支援的 GUIDE_MODEL_PROVIDER：{provider}")
