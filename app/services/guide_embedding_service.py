from io import BytesIO
from pathlib import Path

import numpy as np
from google.genai import types
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings
from app.services.guide_model_service import get_guide_model

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_SUPPORT_ENABLED = True
except ImportError:
    HEIF_SUPPORT_ENABLED = False


class GuideGeminiEmbedding2Service:
    """
    Guide 專用 Gemini Embedding 2 service。

    這個 service 支援：
    1. 文字查詢 embedding
    2. 文字知識庫 embedding
    3. 本機圖片檔 embedding，保留舊版相容
    4. 圖片 bytes embedding，用於 Azure Blob 圖片與使用者上傳圖片，不需要寫入 uploads
    """

    def __init__(self):
        self.client = get_guide_model("gemini")
        self.model_name = settings.GUIDE_GEMINI_EMBEDDING_MODEL
        self.output_dimensionality = settings.GUIDE_EMBEDDING_DIM

    def _config(self):
        return types.EmbedContentConfig(
            output_dimensionality=self.output_dimensionality
        )

    @staticmethod
    def _extract_embedding_values(result) -> list[float]:
        if not getattr(result, "embeddings", None):
            raise RuntimeError("Gemini API 沒有回傳 embeddings。")

        embedding_obj = result.embeddings[0]

        if hasattr(embedding_obj, "values"):
            return list(embedding_obj.values)

        if isinstance(embedding_obj, dict) and "values" in embedding_obj:
            return list(embedding_obj["values"])

        raise RuntimeError(f"無法解析 Gemini embedding 回傳格式：{type(embedding_obj)}")

    def embed_text(self, text: str, title: str | None = None) -> np.ndarray:
        text = text.strip()
        if not text:
            raise ValueError("embed_text 收到空文字。")

        content = f"title: {title or 'none'} | text: {text}"

        result = self.client.models.embed_content(
            model=self.model_name,
            contents=content,
            config=self._config(),
        )

        return np.array(self._extract_embedding_values(result), dtype="float32")

    def embed_query(self, query: str) -> np.ndarray:
        query = query.strip()
        if not query:
            raise ValueError("embed_query 收到空問題。")

        content = f"task: search result | query: {query}"

        result = self.client.models.embed_content(
            model=self.model_name,
            contents=content,
            config=self._config(),
        )

        return np.array(self._extract_embedding_values(result), dtype="float32")

    @staticmethod
    def _image_to_supported_bytes(image_path: Path) -> tuple[bytes, str]:
        suffix = image_path.suffix.lower()

        if suffix in [".jpg", ".jpeg"]:
            return image_path.read_bytes(), "image/jpeg"

        if suffix == ".png":
            return image_path.read_bytes(), "image/png"

        return GuideGeminiEmbedding2Service._image_bytes_to_supported_bytes(
            image_bytes=image_path.read_bytes(),
            filename=image_path.name,
            mime_type=None,
        )

    @staticmethod
    def _image_bytes_to_supported_bytes(
        image_bytes: bytes,
        filename: str | None = None,
        mime_type: str | None = None,
    ) -> tuple[bytes, str]:
        """
        將圖片 bytes 轉成 Gemini 較穩定支援的格式。

        - JPG / PNG：直接送出
        - HEIC / HEIF / WEBP / BMP / TIFF：用 Pillow 在記憶體中轉 PNG
        - 不會寫入本機 uploads
        """
        filename = filename or "uploaded_image"
        suffix = Path(filename).suffix.lower()
        mime_type = (mime_type or "").lower()

        if suffix in [".jpg", ".jpeg"] or mime_type == "image/jpeg":
            return image_bytes, "image/jpeg"

        if suffix == ".png" or mime_type == "image/png":
            return image_bytes, "image/png"

        if suffix in [".heic", ".heif"] and not HEIF_SUPPORT_ENABLED:
            raise RuntimeError(
                "目前環境尚未安裝 pillow-heif，無法讀取 HEIC / HEIF 圖片。"
            )

        try:
            with Image.open(BytesIO(image_bytes)) as img:
                img = ImageOps.exif_transpose(img)
                img = img.convert("RGB")

                buffer = BytesIO()
                img.save(buffer, format="PNG")
                return buffer.getvalue(), "image/png"

        except UnidentifiedImageError as e:
            raise ValueError(f"無法辨識圖片格式：{filename}") from e

    def embed_image_file(self, image_path: str | Path) -> np.ndarray:
        """保留舊版本機檔案 embedding 介面。正式查詢上傳圖片時請用 embed_image_bytes。"""
        image_path = Path(image_path)

        if not image_path.exists():
            raise FileNotFoundError(f"找不到圖片：{image_path}")

        image_bytes, mime_type = self._image_to_supported_bytes(image_path)
        return self.embed_image_bytes(
            image_bytes=image_bytes,
            mime_type=mime_type,
            filename=image_path.name,
        )

    def embed_image_bytes(
        self,
        image_bytes: bytes,
        mime_type: str | None = None,
        filename: str | None = None,
    ) -> np.ndarray:
        """直接將圖片 bytes 建立 embedding，不儲存使用者上傳檔案。"""
        if not image_bytes:
            raise ValueError("embed_image_bytes 收到空圖片 bytes。")

        supported_bytes, supported_mime_type = self._image_bytes_to_supported_bytes(
            image_bytes=image_bytes,
            filename=filename,
            mime_type=mime_type,
        )

        result = self.client.models.embed_content(
            model=self.model_name,
            contents=[
                types.Part.from_bytes(
                    data=supported_bytes,
                    mime_type=supported_mime_type,
                )
            ],
            config=self._config(),
        )

        return np.array(self._extract_embedding_values(result), dtype="float32")


def get_guide_embedding_model(provider: str | None = None):
    provider = (provider or settings.GUIDE_EMBEDDING_PROVIDER).lower().strip()

    if provider == "gemini":
        return GuideGeminiEmbedding2Service()

    raise ValueError(f"目前不支援的 GUIDE_EMBEDDING_PROVIDER：{provider}")
