from fastapi import UploadFile

from app.core.config import settings
from app.enums.speech_type import SpeechType
from app.services.azure_speech_to_text_service import azure_speech_to_text_service
from app.services.gemini_speech_to_text_service import gemini_speech_to_text_service


class SpeechToTextService:

    async def transcribe_upload_file(
        self,
        file: UploadFile,
    ) -> dict:
        provider = (settings.SPEECH_PROVIDER or SpeechType.AZURE.value).lower()

        print("目前 Speech Provider:", provider)

        if provider == SpeechType.AZURE.value:
            return await azure_speech_to_text_service.transcribe_upload_file(file)

        if provider == SpeechType.GEMINI.value:
            return await gemini_speech_to_text_service.transcribe_upload_file(file)

        return {
            "text": f"不支援的 Speech Provider：{provider}",
            "language": "zh-TW",
        }


speech_to_text_service = SpeechToTextService()