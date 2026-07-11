import json

from google.cloud import translate_v3 as translate
from google.oauth2 import service_account

from app.core.config import settings
from app.services.translators.base_translator import BaseTranslator


class GoogleTranslatorService(BaseTranslator):
    def __init__(self):
        credentials_info = json.loads(settings.GOOGLE_CREDENTIALS_JSON)

        credentials = service_account.Credentials.from_service_account_info(
            credentials_info
        )

        self.client = translate.TranslationServiceClient(
            credentials=credentials
        )

        self.project_id = settings.GOOGLE_CLOUD_PROJECT
        self.parent = f"projects/{self.project_id}/locations/global"

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

    def to_google_language(self, language: str | None) -> str:
        language = self.normalize_language(language)

        mapping = {
            "zh-TW": "zh-TW",
            "en-US": "en",
            "ja-JP": "ja",
            "ko-KR": "ko",
        }

        return mapping.get(language, "zh-TW")

    def detect_language(self, text: str) -> str:
        if not text:
            return "zh-TW"

        try:
            response = self.client.detect_language(
                request={
                    "parent": self.parent,
                    "content": text,
                    "mime_type": "text/plain",
                }
            )

            if not response.languages:
                return "zh-TW"

            most_likely = max(response.languages, key=lambda lang: lang.confidence)
            return self.normalize_language(most_likely.language_code)

        except Exception as ex:
            print(f"[GoogleTranslator] detect_language error: {ex}")
            return "zh-TW"

    def translate(
        self,
        text: str,
        target_language: str,
        source_language: str | None = None,
    ) -> str:
        if not text:
            return text

        try:
            response = self.client.translate_text(
                request={
                    "parent": self.parent,
                    "contents": [text],
                    "mime_type": "text/plain",
                    "target_language_code": self.to_google_language(target_language),
                }
            )

            return response.translations[0].translated_text

        except Exception as ex:
            print(f"[GoogleTranslator] translate error: {ex}")
            return text

    def translate_batch(
        self,
        texts: list[str],
        target_language: str,
        source_language: str | None = None,
    ) -> list[str]:
        if not texts:
            return []

        try:
            response = self.client.translate_text(
                request={
                    "parent": self.parent,
                    "contents": texts,
                    "mime_type": "text/plain",
                    "target_language_code": self.to_google_language(target_language),
                }
            )

            return [
                translation.translated_text
                for translation in response.translations
            ]

        except Exception as ex:
            print(f"[GoogleTranslator] translate_batch error: {ex}")
            return texts