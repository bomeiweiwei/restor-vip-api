from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.schemas.guide import GuideAnalyzeResponse
from app.services.guide_image_service import guide_image_service
from app.services.guide_service import get_guide_service

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
    guide_service = get_guide_service()
    return await guide_service.analyze(
        language=language,
        image=image,
        text=text,
        voice=voice,
        attraction_title=attraction_title,
        user_name=user_name,
        history=history,
    )


@router.get("/images/{image_path:path}")
def get_guide_image(image_path: str):
    # 圖片是由瀏覽器直接載入，通常不會帶 Authorization header。
    # 這裡不掛 get_current_user，但 guide_image_service 會限制只能讀專案內的圖片檔。
    return guide_image_service.get_image_response(image_path)


@router.get("/converted-images/{filename}")
def get_guide_converted_image(filename: str):
    # HEIC 轉 JPG 後的圖片同樣由瀏覽器直接載入。
    return guide_image_service.get_converted_image_response(filename)
