from app.core.config import settings
from app.enums.tts_type import TtsType
from app.services.azure_openai_tts_service import (
    azure_openai_tts_service,
)
from app.services.gemini_tts_service import get_gemini_tts_service


class TextToSpeechService:
    def synthesize(self, text: str, language: str = "zh-TW") -> tuple[bytes, str]:
        if settings.TTS_PROVIDER == TtsType.GEMINI:
            audio = get_gemini_tts_service().synthesize(text, language)
            return audio, "audio/wav"

        if settings.TTS_PROVIDER == TtsType.AZURE:
            audio = azure_openai_tts_service.synthesize(text)
            return audio, "audio/mpeg"

        raise ValueError(f"不支援的 TTS_PROVIDER: {settings.TTS_PROVIDER}")


text_to_speech_service = TextToSpeechService()