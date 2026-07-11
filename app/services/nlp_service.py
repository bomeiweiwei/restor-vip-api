from app.services.translator_factory import get_translator


class NlpService:
    def __init__(self):
        self.translator = get_translator()

    def normalize_language(self, language: str | None) -> str:
        return self.translator.normalize_language(language)

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
        language = self.translator.detect_language(text)
        zh_text = self.translator.translate(text, "zh-TW")

        return {
            "original_text": text,
            "language": language,
            "zh_text": zh_text,
        }

    def translate_reply(self, text: str, target_language: str) -> str:
        target_language = self.translator.normalize_language(target_language)

        if target_language == "zh-TW":
            return text

        return self.translator.translate(text, target_language)


nlp_service = NlpService()
