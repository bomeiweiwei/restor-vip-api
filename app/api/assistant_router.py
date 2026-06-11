from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session

from app.core.database import get_db

from app.schemas.assistant import (
    AssistantRequest,
    AssistantResponse,
    SpeechToTextResponse,
)

from app.services.assistant_service import (
    assistant_service,
)

from app.dependencies.auth_dependency import get_current_user

router = APIRouter(
    prefix="/api/assistant",
    tags=["Assistant"],
)


@router.post(
    "/speech-to-text",
    response_model=SpeechToTextResponse,
)
async def speech_to_text(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):

    return await assistant_service.speech_to_text(file)


@router.post(
    "/send-msg",
    response_model=AssistantResponse,
)
def send_msg(
    request: AssistantRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):

    return assistant_service.send_message(request.message)
