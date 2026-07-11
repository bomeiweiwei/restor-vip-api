from azure.ai.translation.text import TextTranslationClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError

from app.core.config import settings
from app.services.translators.base_translator import BaseTranslator


class AzureTranslatorService(BaseTranslator):
    def __init__(self):
        self.client = TextTranslationClient(
            credential=AzureKeyCredential(settings.AZURE_TRANSLATOR_KEY),
            endpoint=settings.AZURE_TRANSLATOR_ENDPOINT,
            region=settings.AZURE_TRANSLATOR_REGION,
        )

    def normalize_language(self, language: str | None) -> str:
        if not language:
            return "zh-TW"

        language = language.strip()

        if language in ("zh-Hant", "zh-Hans", "zh", "zh-TW", "zh-CN"):
            return "zh-TW"

        if language.startswith("ja"):
            return "ja-JP"

        if language.startswith("ko"):
            return "ko-KR"

        if language.startswith("en"):
            return "en-US"

        return "zh-TW"

    def to_azure_language(self, language: str | None) -> str:
        language = self.normalize_language(language)

        mapping = {
            "zh-TW": "zh-Hant",
            "en-US": "en",
            "ja-JP": "ja",
            "ko-KR": "ko",
        }

        return mapping.get(language, "zh-Hant")

    def detect_language(self, text: str) -> str:
        if not text:
            return "zh-TW"

        try:
            response = self.client.translate(
                body=[text],
                to_language=["zh-Hant"],
            )

            return self.normalize_language(response[0].detected_language.language)

        except HttpResponseError as ex:
            print(f"[AzureTranslator] detect_language error: {ex}")
            return "zh-TW"

    def translate(
        self,
        text: str,
        target_language: str,
        source_language: str | None = None,
    ) -> str:
        if not text:
            return text

        target_language = self.normalize_language(target_language)

        try:
            response = self.client.translate(
                body=[text],
                to_language=[self.to_azure_language(target_language)],
            )

            return response[0].translations[0].text

        except HttpResponseError as ex:
            print(f"[AzureTranslator] translate error: {ex}")
            return text

    def translate_batch(
        self,
        texts: list[str],
        target_language: str,
        source_language: str | None = None,
    ) -> list[str]:
        if not texts:
            return []

        target_language = self.normalize_language(target_language)

        try:
            response = self.client.translate(
                body=texts,
                to_language=[self.to_azure_language(target_language)],
            )

            return [
                item.translations[0].text
                for item in response
            ]

        except HttpResponseError as ex:
            print(f"[AzureTranslator] translate_batch error: {ex}")
            return texts