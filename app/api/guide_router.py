from fastapi import APIRouter, Depends, UploadFile, File, Form, Response, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.schemas.guide import GuideAnalyzeResponse, GuideTextToSpeechRequest
from app.services.guide_service import guide_service
from app.services.guide_image_service import guide_image_service

from app.services.text_to_speech_service import text_to_speech_service

router = APIRouter(
    prefix="/api/guide",
    tags=["Guide"],
)


@router.post(
    "/analyze",
    response_model=GuideAnalyzeResponse,
)
async def analyze_guide(
    language: str = Form("zh-TW"),
    image: UploadFile | None = File(None),
    text: str | None = Form(None),
    voice: UploadFile | None = File(None),
    attraction_title: str | None = Form(None),
    user_name: str | None = Form(None),
    history: str | None = Form(None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    
    return await guide_service.analyze(
        db=db,
        current_user=current_user,
        language=language,
        image=image,
        text=text,
        voice=voice,
        attraction_title=attraction_title,
        user_name=user_name,
        history=history,
    )


@router.post("/text-to-speech")
async def guide_text_to_speech_api(
    request: GuideTextToSpeechRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    專屬導遊專用 TTS。
    不儲存音檔，直接回傳 audio/mpeg 給前端播放。
    """
    try:
        if not request.text or not request.text.strip():
            raise HTTPException(
                status_code=400,
                detail="沒有可轉換成語音的導覽文字。",
            )

        print("[GUIDE TTS] language =", request.language)
        print("[GUIDE TTS] text length =", len(request.text))

        audio_bytes, media_type = text_to_speech_service.synthesize(
            text=request.text,
            language=request.language,
        )

        if not audio_bytes:
            raise HTTPException(
                status_code=500,
                detail="專屬導遊語音合成失敗，audio_bytes 為空。",
            )

        return Response(
            content=audio_bytes,
            media_type=media_type,
        )

    except RuntimeError as e:
        print("[GUIDE TTS ERROR]", str(e))
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )

    except Exception as e:
        print("[GUIDE TTS UNKNOWN ERROR]", repr(e))
        raise HTTPException(
            status_code=500,
            detail=f"專屬導遊語音合成發生未知錯誤：{str(e)}",
        )


@router.get("/images/{image_path:path}")
def get_guide_image(image_path: str):
    """
    讀取原始圖片。

    例如：
    /api/guide/images/data/raw/RAG知識庫/.../main.JPG
    """
    return guide_image_service.get_image_response(image_path)


@router.get("/converted-images/{filename}")
def get_guide_converted_image(filename: str):
    """
    讀取 HEIC / HEIF 轉換後的 JPG 圖片。

    例如：
    /api/guide/converted-images/main_xxxxx.jpg
    """
    return guide_image_service.get_converted_image_response(filename)