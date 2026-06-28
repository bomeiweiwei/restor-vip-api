# app/utils/image_url.py

from app.core.config import settings


def build_image_url(pic_url: str | None) -> str:
    asset_base_url = settings.ASSET_BASE_URL.rstrip("/")

    if not pic_url:
        return f"{asset_base_url}/images/empty.png"

    if pic_url.startswith("http"):
        return pic_url

    # 相容舊資料：/static/images/31.png -> /images/31.png
    normalized = pic_url.replace("/static", "", 1)

    if not normalized.startswith("/"):
        normalized = "/" + normalized

    return f"{asset_base_url}{normalized}"