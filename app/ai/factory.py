from app.enums.ai_type import AiType

from app.ai.base import BaseAILangchain

from app.ai.lmstudio_langchain import LMStudioLangchain
from app.ai.azure_langchain import AzureLangchain
from app.ai.gemini_langchain import GeminiLangchain

from app.core.config import settings


def create_ai_langchain(ai_type: AiType | str) -> BaseAILangchain:

    ai_type = AiType(ai_type)

    if ai_type == AiType.GEMINI:
        return GeminiLangchain(
            api_key=settings.GEMINI_API_KEY,
            model_name=settings.GEMINI_MODEL_NAME,
        )

    if ai_type == AiType.AZURE:
        return AzureLangchain(
            api_key=settings.AZURE_OPENAI_API_KEY,
            endpoint=settings.AZURE_OPENAI_BASE_URL,
            deployment_name=settings.AZURE_OPENAI_DEPLOYMENT_NAME
        )

    if ai_type == AiType.LMSTUDIO:
        return LMStudioLangchain(
            base_url=settings.LMSTUDIO_BASE_URL,
            api_key=settings.LMSTUDIO_API_KEY,
            model_name=settings.LMSTUDIO_MODEL_NAME,
        )

    raise ValueError(f"不支援的 AI 類型：{ai_type}")