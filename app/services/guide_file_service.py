import mimetypes
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings


DOCUMENT_EXTENSIONS = {
    ".txt", ".pdf", ".doc", ".docx", ".ppt", ".pptx",
    ".xls", ".xlsx", ".csv", ".md", ".json",
}

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif",
}

UPLOAD_SUBFOLDERS = {
    "image": "images",
    "audio": "audios",
    "video": "videos",
    "document": "documents",
    "other": "others",
}


@dataclass
class GuideSavedFile:
    label: str
    original_name: str
    filename: str
    folder: str
    mime_type: str
    kind: str
    saved_path: str

    def to_input_item(self) -> dict:
        return {
            "label": self.label,
            "original_name": self.original_name,
            "filename": self.filename,
            "folder": self.folder,
            "mime_type": self.mime_type,
            "kind": self.kind,
            "saved_path": self.saved_path,
        }


class GuideFileService:
    def project_root(self) -> Path:
        return Path(settings.GUIDE_PROJECT_ROOT).resolve()

    def upload_root(self) -> Path:
        path = Path(settings.GUIDE_UPLOAD_DIR)
        if not path.is_absolute():
            path = self.project_root() / path
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()

    @staticmethod
    def safe_filename(original_filename: str, default_extension: str = "bin") -> str:
        original_filename = original_filename or "uploaded_file"
        stem = Path(original_filename).stem or "uploaded_file"
        suffix = Path(original_filename).suffix.lstrip(".") or default_extension

        # 保留中文、英文、數字、底線與連字號，避免 Windows / URL 特殊字元問題。
        safe_stem = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff-]+", "_", stem).strip("_")
        if not safe_stem:
            safe_stem = "uploaded_file"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_id = uuid.uuid4().hex[:8]
        return f"{timestamp}_{random_id}_{safe_stem}.{suffix}"

    @staticmethod
    def guess_mime_type(filename: str, file_content_type: str | None = None) -> str:
        if file_content_type:
            return file_content_type

        guessed_type, _ = mimetypes.guess_type(filename or "")
        return guessed_type or "application/octet-stream"

    @staticmethod
    def classify_file_type(filename: str, mime_type: str) -> str:
        extension = os.path.splitext(filename or "")[1].lower()

        # HEIC / HEIF 有時會是 application/octet-stream，所以先看副檔名。
        if extension in IMAGE_EXTENSIONS or mime_type.startswith("image/"):
            return "image"
        if mime_type.startswith("audio/"):
            return "audio"
        if mime_type.startswith("video/"):
            return "video"
        if extension in DOCUMENT_EXTENSIONS:
            return "document"

        return "other"

    @staticmethod
    def preview_kind(file_type: str) -> str:
        if file_type == "image":
            return "image"
        if file_type == "audio":
            return "audio"
        if file_type == "video":
            return "video"
        return "file"

    def to_project_relative_path(self, path: str | Path) -> str:
        path_obj = Path(path).resolve()
        try:
            return path_obj.relative_to(self.project_root()).as_posix()
        except ValueError:
            return str(path_obj).replace("\\", "/")

    async def save_upload_file(self, upload_file: UploadFile, label: str) -> GuideSavedFile | None:
        if not upload_file or not upload_file.filename:
            return None

        content = await upload_file.read()
        if not content:
            return None

        mime_type = self.guess_mime_type(upload_file.filename, upload_file.content_type)
        file_type = self.classify_file_type(upload_file.filename, mime_type)
        subfolder = UPLOAD_SUBFOLDERS[file_type]

        filename = self.safe_filename(upload_file.filename)
        save_dir = self.upload_root() / subfolder
        save_dir.mkdir(parents=True, exist_ok=True)

        save_path = save_dir / filename
        save_path.write_bytes(content)

        return GuideSavedFile(
            label=label,
            original_name=upload_file.filename,
            filename=filename,
            folder=subfolder,
            mime_type=mime_type,
            kind=self.preview_kind(file_type),
            saved_path=self.to_project_relative_path(save_path),
        )


guide_file_service = GuideFileService()
