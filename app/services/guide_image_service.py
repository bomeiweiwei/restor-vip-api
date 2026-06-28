from io import BytesIO
import mimetypes
from pathlib import Path
from urllib.parse import quote

from azure.storage.blob import BlobServiceClient
from fastapi import HTTPException
from fastapi.responses import Response

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
    """
    Guide 代表圖片讀取服務。

    正式模式：
    - metadata 的 source_path 會被視為 Azure Blob name，例如 data/raw/RAG知識庫/.../images/main.JPG。
    - 不再從本機 data/raw 讀圖片。
    - HEIC / HEIF 圖片會在記憶體中轉成 JPG 後回傳，不寫入本機 converted_images。

    舊版本機設定保留備查，不再於正式流程使用：
    # GUIDE_CONVERTED_IMAGE_DIR=data/processed/converted_images
    # /api/guide/converted-images/{filename}
    """

    def __init__(self):
        self._blob_service_client: BlobServiceClient | None = None
        self._container_client = None

    @property
    def container_client(self):
        if self._container_client is None:
            if not settings.AZURE_STORAGE_CONNECTION_STRING:
                raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING 尚未設定。")
            if not settings.AZURE_STORAGE_CONTAINER_NAME:
                raise RuntimeError("AZURE_STORAGE_CONTAINER_NAME 尚未設定。")

            self._blob_service_client = BlobServiceClient.from_connection_string(
                settings.AZURE_STORAGE_CONNECTION_STRING
            )
            self._container_client = self._blob_service_client.get_container_client(
                settings.AZURE_STORAGE_CONTAINER_NAME
            )
        return self._container_client

    @staticmethod
    def _normalize_blob_image_path(image_path: str | None) -> str | None:
        if not image_path:
            return None

        blob_name = str(image_path).replace("\\", "/").lstrip("/")

        # 只允許讀取 data/ 底下的知識庫圖片，避免把 API 變成任意 Blob 下載器。
        data_prefix = str(getattr(settings, "GUIDE_BLOB_DATA_PREFIX", "data/") or "data/").strip("/") + "/"
        if not blob_name.startswith(data_prefix):
            return None

        if Path(blob_name).suffix.lower() not in IMAGE_EXTENSIONS:
            return None

        return blob_name

    def _download_blob_bytes(self, blob_name: str) -> bytes:
        try:
            blob_client = self.container_client.get_blob_client(blob_name)
            return blob_client.download_blob().readall()
        except Exception as e:
            raise HTTPException(
                status_code=404,
                detail=f"找不到 Azure Blob 圖片：{blob_name}，原因：{e}",
            ) from e

    @staticmethod
    def _convert_image_bytes_to_jpeg(image_bytes: bytes, source_name: str) -> bytes:
        if not HEIC_CONVERT_AVAILABLE:
            raise RuntimeError("尚未安裝 Pillow 或 pillow-heif，無法轉換 HEIC / HEIF。")

        try:
            with Image.open(BytesIO(image_bytes)) as image:
                image = ImageOps.exif_transpose(image)
                if image.mode != "RGB":
                    image = image.convert("RGB")

                buffer = BytesIO()
                image.save(buffer, format="JPEG", quality=90, optimize=True)
                return buffer.getvalue()
        except Exception as e:
            raise RuntimeError(f"圖片轉 JPG 失敗：{source_name}，原因：{e}") from e

    def image_path_to_url(self, image_path: str | None) -> str | None:
        """把 Qdrant payload 的 source_path 轉成前端可讀取的 API URL。"""
        blob_name = self._normalize_blob_image_path(image_path)
        if blob_name is None:
            return None

        # 讓 /api/guide/images/{image_path:path} 直接處理原圖；HEIC 也由同一個 endpoint 即時轉 JPG。
        return f"/api/guide/images/{quote(blob_name, safe='/')}"

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

    def get_image_response(self, image_path: str) -> Response:
        """從 Azure Blob 讀取代表圖片並回傳給前端。"""
        blob_name = self._normalize_blob_image_path(image_path)
        if blob_name is None:
            raise HTTPException(status_code=403, detail="不允許讀取此圖片路徑或檔案類型")

        suffix = Path(blob_name).suffix.lower()
        image_bytes = self._download_blob_bytes(blob_name)

        if suffix in HEIC_EXTENSIONS:
            try:
                jpg_bytes = self._convert_image_bytes_to_jpeg(image_bytes, blob_name)
            except RuntimeError as e:
                raise HTTPException(status_code=500, detail=str(e)) from e

            return Response(content=jpg_bytes, media_type="image/jpeg")

        media_type = mimetypes.guess_type(blob_name)[0] or "application/octet-stream"
        return Response(content=image_bytes, media_type=media_type)

    def get_converted_image_response(self, filename: str) -> Response:
        """
        舊版 HEIC converted-images endpoint。
        正式 Azure Blob 模式不再產生本機 converted 圖片，請改用 /api/guide/images/{path}。
        """
        raise HTTPException(
            status_code=410,
            detail="converted-images 已停用；HEIC / HEIF 會由 /api/guide/images/{image_path} 即時轉換。",
        )


guide_image_service = GuideImageService()
