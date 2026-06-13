from fastapi import UploadFile

from app.schemas.assistant import (
    SpeechToTextResponse,
    AssistantResponse,
)

from app.services.speech_to_text_service import speech_to_text_service
from app.services.judge_user_input_service import judge_user_input_service


class AssistantService:

    async def speech_to_text(
        self,
        file: UploadFile,
    ) -> AssistantResponse:

        result = await speech_to_text_service.transcribe_upload_file(file)

        text = result["text"]
        language = result["language"]

        response = judge_user_input_service.judge(text)

        return AssistantResponse(
            reply=response.reply,
            language=language,
        )

    def send_message(
        self,
        message: str,
    ) -> AssistantResponse:

        return judge_user_input_service.judge(message)


assistant_service = AssistantService()