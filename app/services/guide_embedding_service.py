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

    保留新人專案 AI Studio API Key 呼叫方式，避免和正式後端
    app/ai/embedding_factory.py 的 Vertex AI 設定互相影響。
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

        if suffix in [".heic", ".heif"] and not HEIF_SUPPORT_ENABLED:
            raise RuntimeError(
                "目前環境尚未安裝 pillow-heif，無法讀取 HEIC / HEIF 圖片。"
            )

        try:
            with Image.open(image_path) as img:
                img = ImageOps.exif_transpose(img)
                img = img.convert("RGB")

                buffer = BytesIO()
                img.save(buffer, format="PNG")
                return buffer.getvalue(), "image/png"

        except UnidentifiedImageError as e:
            raise ValueError(f"無法辨識圖片格式：{image_path}") from e

    def embed_image_file(self, image_path: str | Path) -> np.ndarray:
        image_path = Path(image_path)

        if not image_path.exists():
            raise FileNotFoundError(f"找不到圖片：{image_path}")

        image_bytes, mime_type = self._image_to_supported_bytes(image_path)

        result = self.client.models.embed_content(
            model=self.model_name,
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type,
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
