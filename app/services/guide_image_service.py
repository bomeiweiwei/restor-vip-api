import hashlib
import mimetypes
import re
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings

try:
    from PIL import Image, ImageOps
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIC_CONVERT_AVAILABLE = True
except ImportError:
    Image = None
    ImageOps = None
    HEIC_CONVERT_AVAILABLE = False


IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif",
}

HEIC_EXTENSIONS = {".heic", ".heif"}


class GuideImageService:
    def project_root(self) -> Path:
        return Path(settings.GUIDE_PROJECT_ROOT).resolve()

    def converted_image_root(self) -> Path:
        path = Path(settings.GUIDE_CONVERTED_IMAGE_DIR)
        if not path.is_absolute():
            path = self.project_root() / path
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()

    def resolve_project_image_path(self, image_path: str | None) -> Path | None:
        if not image_path:
            return None

        normalized = str(image_path).replace("\\", "/").lstrip("/")
        requested_path = (self.project_root() / normalized).resolve()

        # 限制只能讀取專案內檔案，避免路徑穿越。
        try:
            requested_path.relative_to(self.project_root())
        except ValueError:
            return None

        if requested_path.is_file():
            return requested_path

        # 支援 .jpg / .JPG 大小寫差異。
        parent = requested_path.parent
        target_name_lower = requested_path.name.lower()
        if parent.is_dir():
            for child in parent.iterdir():
                if child.is_file() and child.name.lower() == target_name_lower:
                    return child.resolve()

        return None

    def convert_heic_to_jpg(self, source_path: Path) -> Path:
        if not HEIC_CONVERT_AVAILABLE:
            raise RuntimeError("尚未安裝 Pillow 或 pillow-heif，無法轉換 HEIC / HEIF。")

        source_path = source_path.resolve()
        cache_key_text = f"{source_path}|{source_path.stat().st_mtime_ns}"
        cache_key = hashlib.sha1(cache_key_text.encode("utf-8")).hexdigest()[:16]

        safe_stem = re.sub(
            r"[^a-zA-Z0-9_\u4e00-\u9fff-]+",
            "_",
            source_path.stem,
        ).strip("_") or "converted_image"

        output_path = self.converted_image_root() / f"{safe_stem}_{cache_key}.jpg"

        if output_path.is_file() and output_path.stat().st_size > 0:
            return output_path

        with Image.open(source_path) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode != "RGB":
                image = image.convert("RGB")
            image.save(output_path, format="JPEG", quality=90, optimize=True)

        return output_path

    def image_path_to_url(self, image_path: str | None) -> str | None:
        existing_path = self.resolve_project_image_path(image_path)
        if existing_path is None:
            return None

        suffix = existing_path.suffix.lower()

        if suffix in HEIC_EXTENSIONS:
            jpg_path = self.convert_heic_to_jpg(existing_path)
            return f"/guide/converted-images/{quote(jpg_path.name)}"

        relative_path = existing_path.relative_to(self.project_root()).as_posix()
        return f"/guide/images/{quote(relative_path, safe='/')}"

    def attach_representative_image_url(self, place_result: dict) -> dict:
        result = dict(place_result or {})
        image_paths = list(result.get("representative_image_paths") or [])

        single_image_path = result.get("representative_image_path")
        if single_image_path and single_image_path not in image_paths:
            image_paths.insert(0, single_image_path)

        image_urls = []
        for image_path in image_paths:
            try:
                image_url = self.image_path_to_url(image_path)
            except Exception as e:
                print(f"[GUIDE IMAGE URL ERROR] {image_path} -> {e}")
                image_url = None

            if image_url and image_url not in image_urls:
                image_urls.append(image_url)

        result["representative_image_urls"] = image_urls
        result["representative_image_url"] = image_urls[0] if image_urls else ""
        return result

    def get_image_response(self, image_path: str) -> FileResponse:
        path = self.resolve_project_image_path(image_path)
        if path is None or not path.is_file():
            raise HTTPException(status_code=404, detail="找不到圖片")

        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise HTTPException(status_code=403, detail="不允許讀取此檔案類型")

        # HEIC 不直接回給瀏覽器，請透過 image_path_to_url 轉成 converted-images。
        if path.suffix.lower() in HEIC_EXTENSIONS:
            converted = self.convert_heic_to_jpg(path)
            return FileResponse(converted, media_type="image/jpeg")

        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return FileResponse(path, media_type=media_type)

    def get_converted_image_response(self, filename: str) -> FileResponse:
        converted_root = self.converted_image_root()
        requested_path = (converted_root / filename).resolve()

        try:
            requested_path.relative_to(converted_root)
        except ValueError:
            raise HTTPException(status_code=403, detail="不允許讀取此路徑")

        if not requested_path.is_file():
            raise HTTPException(status_code=404, detail="找不到轉換後圖片")

        if requested_path.suffix.lower() not in {".jpg", ".jpeg"}:
            raise HTTPException(status_code=403, detail="不允許讀取此檔案類型")

        return FileResponse(requested_path, media_type="image/jpeg")


guide_image_service = GuideImageService()
