from fastapi import APIRouter, Depends, UploadFile, File, Response, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db

from app.schemas.assistant import (
    AssistantRequest,
    AssistantResponse,
    TextToSpeechRequest,
)

from app.services.assistant_service import (
    assistant_service,
)

from app.services.text_to_speech_service import text_to_speech

from app.dependencies.auth_dependency import get_current_user

from app.utils.text_to_speech_utils import clean_tts_text

router = APIRouter(
    prefix="/api/assistant",
    tags=["Assistant"],
)


@router.post(
    "/speech-to-text",
    response_model=AssistantResponse,
)
async def speech_to_text(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):

    return await assistant_service.speech_to_text(
        db=db, current_user=current_user, file=file
    )


@router.post(
    "/send-msg",
    response_model=AssistantResponse,
)
def send_msg(
    request: AssistantRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):

    return assistant_service.send_message(
        db=db, current_user=current_user, message=request.message
    )


@router.post("/text-to-speech")
async def text_to_speech_api(
    request: TextToSpeechRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        audio_bytes = text_to_speech(
            text=clean_tts_text(request.text),
            language=request.language,
        )

        if not audio_bytes:
            raise HTTPException(
                status_code=500,
                detail="語音合成失敗",
            )

        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
        )

    except RuntimeError as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
