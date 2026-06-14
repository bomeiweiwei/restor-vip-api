from azure.ai.translation.text import TextTranslationClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError

from app.core.config import settings


class NlpService:
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

    def analyze_user_text(self, text: str) -> dict:
        """
        偵測使用者語言，並轉成繁體中文。
        回傳：
        {
            "original_text": 原文,
            "language": 使用者語言,
            "zh_text": 繁中內容
        }
        """
        try:
            response = self.client.translate(
                body=[text],
                to_language=["zh-Hant"],
            )

            result = response[0]
            language = self.normalize_language(
                result.detected_language.language
            )

            zh_text = result.translations[0].text

            return {
                "original_text": text,
                "language": language,
                "zh_text": zh_text,
            }

        except HttpResponseError as ex:
            print(f"[NLP] Azure Translator error: {ex}")
            return {
                "original_text": text,
                "language": "zh-Hant",
                "zh_text": text,
            }

    def translate_reply(self, text: str, target_language: str) -> str:
        target_language = self.normalize_language(target_language)

        if target_language == "zh-TW":
            return text

        try:
            response = self.client.translate(
                body=[text],
                to_language=[self.to_azure_language(target_language)],
            )

            return response[0].translations[0].text

        except HttpResponseError as ex:
            print(f"[NLP] Reply translate error: {ex}")
            return text


nlp_service = NlpService()