from fastapi import UploadFile

from app.schemas.assistant import (
    SpeechToTextResponse,
    AssistantResponse,
)

from app.services.speech_to_text_service import speech_to_text_service


class AssistantService:

    async def speech_to_text(
        self,
        file: UploadFile,
    ) -> SpeechToTextResponse:

        text = await speech_to_text_service.transcribe_upload_file(file)

        return SpeechToTextResponse(text=text)

    def send_message(
        self,
        message: str,
    ) -> AssistantResponse:

        return AssistantResponse(reply=f"已收到您的訊息：{message}")


assistant_service = AssistantService()
