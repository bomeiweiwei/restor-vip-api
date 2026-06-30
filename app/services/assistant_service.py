from fastapi import UploadFile

from app.schemas.assistant import AssistantResponse
from app.services.speech_to_text_service import speech_to_text_service
from app.services.judge_user_input_service import judge_user_input_service
from app.services.nlp_service import nlp_service
from app.utils.markdown_utils import markdown_to_text
from app.services.gemini_tts_service import get_gemini_tts_service

from sqlalchemy.orm import Session


class AssistantService:

    async def speech_to_text(
        self,
        db: Session,
        current_user: dict,
        file: UploadFile,
    ) -> AssistantResponse:

        result = await speech_to_text_service.transcribe_upload_file(file)

        text = result["text"]
        language = result["language"]

        response = judge_user_input_service.judge(
            db=db, current_user=current_user, message=text
        )

        translated_reply = nlp_service.translate_reply(
            text=response.reply,
            target_language=language,
        )

        speech_reply = markdown_to_text(translated_reply)

        audio_base64 = get_gemini_tts_service().synthesize_base64(
            text=speech_reply,
            language=language,
        )

        return AssistantResponse(
            text=text,
            reply=translated_reply,
            speech_reply=speech_reply,
            language=language,
            audio_base64=audio_base64,
        )

    def send_message(
        self,
        db: Session,
        current_user: dict,
        message: str,
    ) -> AssistantResponse:

        nlp_result = nlp_service.analyze_user_text(message)

        response = judge_user_input_service.judge(
            db=db, current_user=current_user, message=nlp_result["zh_text"]
        )

        reply = nlp_service.translate_reply(
            response.reply,
            nlp_result["language"],
        )

        return AssistantResponse(
            reply=reply,
            language=nlp_result["language"],
        )


assistant_service = AssistantService()
