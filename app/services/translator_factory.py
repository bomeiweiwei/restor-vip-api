from app.core.config import settings
from app.enums.translator_type import TranslatorType
from app.services.translators.azure_translator_service import AzureTranslatorService
from app.services.translators.google_translator_service import GoogleTranslatorService
from app.services.translators.base_translator import BaseTranslator


def get_translator() -> BaseTranslator:
    provider = settings.TRANSLATOR_PROVIDER.lower()

    if provider == TranslatorType.GOOGLE.value:
        return GoogleTranslatorService()

    if provider == TranslatorType.AZURE.value:
        return AzureTranslatorService()

    print(f"[TranslatorFactory] Unknown provider: {provider}, fallback to Azure")
    return AzureTranslatorService()