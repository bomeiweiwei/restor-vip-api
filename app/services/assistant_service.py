from fastapi import UploadFile

from app.schemas.assistant import AssistantResponse
from app.services.speech_to_text_service import speech_to_text_service
from app.services.judge_user_input_service import judge_user_input_service
from app.services.nlp_service import nlp_service


class AssistantService:

    async def speech_to_text(
        self,
        file: UploadFile,
    ) -> AssistantResponse:

        result = await speech_to_text_service.transcribe_upload_file(file)

        text = result["text"]
        language = result["language"]

        response = judge_user_input_service.judge(text)

        translated_reply = nlp_service.translate_reply(
            text=response.reply,
            target_language=language,
        )

        return AssistantResponse(
            text=text,
            reply=translated_reply,
            language=language,
        )

    def send_message(
        self,
        message: str,
    ) -> AssistantResponse:

        nlp_result = nlp_service.analyze_user_text(message)

        response = judge_user_input_service.judge(nlp_result["zh_text"])

        reply = nlp_service.translate_reply(
            response.reply,
            nlp_result["language"],
        )

        return AssistantResponse(
            reply=reply,
            language=nlp_result["language"],
        )


assistant_service = AssistantService()
