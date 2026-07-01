import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from pypdf import PdfReader

from app.core.config import settings
from app.services.guide_embedding_service import get_guide_embedding_model
from app.services.guide_image_service import guide_image_service
from app.services.guide_model_service import get_guide_model
from app.services.guide_vector_db_service import GuideVectorDBService
# from app.services.guide_speech_to_text_service import guide_speech_to_text_service
from app.prompts.guide_answer_prompt import build_guide_answer_prompt
from app.utils.markdown_utils import markdown_to_text
from app.services.gemini_tts_service import get_gemini_tts_service

from app.services.speech_to_text_service import speech_to_text_service


IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".heic", ".heif",
}

IMAGE_PRIORITY_KEYWORDS = ["main", "cover", "thumbnail", "thumb", "代表", "封面", "主要"]


class GuideCoreService:
    """
    專屬導遊核心邏輯。

    這份是從測試專案 personal_tour_guide.py 拆出來的 FastAPI 版，
    並保留原本 data/ 架構與 metadata source_path。
    """

    def __init__(self):
        self.embedding_model = get_guide_embedding_model()
        self.vector_db = GuideVectorDBService()

        self.model_provider = (settings.GUIDE_MODEL_PROVIDER or "gemini").lower().strip()
        self.llm_client = get_guide_model(self.model_provider)

        if self.model_provider == "azure":
            self.generation_model = (
                getattr(settings, "AZURE_OPENAI_DEPLOYMENT_NAME", None)
                or getattr(settings, "AZURE_OPENAI_MODEL", None)
                or "gpt-5.1"
            )
        else:
            self.generation_model = settings.GUIDE_GEMINI_GENERATION_MODEL

    def _project_root(self) -> Path:
        return Path(settings.GUIDE_PROJECT_ROOT).resolve()

    def _project_path(self, path: str | Path) -> Path:
        path_obj = Path(str(path).replace("\\", "/"))
        if path_obj.is_absolute():
            return path_obj
        return self._project_root() / path_obj

    def _to_project_relative_path(self, path: str | Path) -> str:
        path_obj = Path(path).resolve()
        try:
            return path_obj.relative_to(self._project_root()).as_posix()
        except ValueError:
            return str(path_obj).replace("\\", "/")

    def _embed_query_text(self, text: str):
        if hasattr(self.embedding_model, "embed_query"):
            return self.embedding_model.embed_query(text)
        return self.embedding_model.embed_text(text=text, title="使用者查詢")

    @staticmethod
    def _normalize_language_code(language: str | None) -> str:
        """把前端或語音辨識回傳的語言代碼統一成 TTS / Prompt 可用格式。"""
        value = (language or "").strip().lower().replace("_", "-")

        if value in {"zh", "zh-tw", "zh-hant", "zh-hant-tw", "tw"}:
            return "zh-TW"
        if value in {"zh-cn", "zh-hans", "zh-hans-cn", "cn"}:
            return "zh-CN"
        if value.startswith("en"):
            return "en-US"
        if value.startswith("ja") or value in {"jp", "japanese"}:
            return "ja-JP"
        if value.startswith("ko") or value in {"kr", "korean"}:
            return "ko-KR"

        return "zh-TW"

    @classmethod
    def _detect_language_from_text(cls, text: str | None, fallback: str = "zh-TW") -> str:
        """依照使用者本次輸入文字，決定回答與 TTS 使用語言。

        這不是完整 NLP 語言偵測，而是專案第一版足夠使用的規則：
        - 日文：平假名 / 片假名
        - 韓文：Hangul
        - 中文：CJK
        - 英文：英文字母
        """
        text = (text or "").strip()
        fallback = cls._normalize_language_code(fallback)

        if not text:
            return fallback

        if re.search(r"[\u3040-\u30ff]", text):
            return "ja-JP"

        if re.search(r"[\uac00-\ud7af]", text):
            return "ko-KR"

        if re.search(r"[\u4e00-\u9fff]", text):
            return "zh-TW"

        if re.search(r"[A-Za-z]", text):
            return "en-US"

        return fallback

    @staticmethod
    def _language_instruction(language: str) -> str:
        normalized = GuideCoreService._normalize_language_code(language)

        if normalized == "en-US":
            return "English only. Use natural English."
        if normalized == "ja-JP":
            return "Japanese only. Use natural Japanese."
        if normalized == "ko-KR":
            return "Korean only. Use natural Korean."
        if normalized == "zh-CN":
            return "Simplified Chinese only."

        return "Traditional Chinese only."


    @staticmethod
    def _normalize_text_for_compare(text: str | None) -> str:
        """把文字轉成適合做地點名稱比對的格式。"""
        text = (text or "").strip().lower()
        text = re.sub(r"[\s\u3000\-－—_、，。！？!?,.：:；;「」『』\"'()（）\[\]【】]+", "", text)
        return text

    @classmethod
    def _normalize_place_alias_for_compare(cls, text: str | None) -> str:
        """把地點名稱轉成適合做「簡稱 / 別名」比對的格式。

        目的：
        - 綠舞觀光渡假村 ≈ 綠舞渡假村
        - 綠舞觀光度假村 ≈ 綠舞渡假村
        - 綠舞觀光渡假村 ≈ 綠舞
        - 蘭陽博物館 ≈ 蘭陽
        """
        normalized = cls._normalize_text_for_compare(text)

        if not normalized:
            return ""

        # 處理常見異體 / 簡繁 / 同義寫法。
        replacements = {
            "度假村": "渡假村",
            "度假": "渡假",
            "绿": "綠",
            "兰": "蘭",
            "馆": "館",
            "饭店": "飯店",
            "酒店": "酒店",
        }
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)

        # 移除常見但不影響地點辨識的修飾詞。
        removable_words = [
            "觀光",
            "国际",
            "國際",
            "休閒",
            "股份有限公司",
            "有限公司",
        ]
        for word in removable_words:
            normalized = normalized.replace(word, "")

        # source_path 可能包含資料夾斜線，別名比對時移除路徑分隔符。
        normalized = re.sub(r"[\\/]+", "", normalized)

        # 移除常見地點尾綴，避免「綠舞渡假村」與「綠舞觀光渡假村」
        # 因中間少了「觀光」而比對失敗。
        generic_suffixes = [
            "渡假村",
            "飯店",
            "酒店",
            "旅館",
            "旅店",
            "園區",
            "中心",
            "展館",
            "藝館",
            "美術館",
            "博物館",
            "老街",
            "夜市",
            "車站",
            "餐廳",
            "遊戲室",
            "浴場",
            "泳池",
            "咖啡",
            "cafe",
            "廳",
            "館",
        ]
        for suffix in generic_suffixes:
            if normalized.endswith(suffix) and len(normalized) > len(suffix) + 1:
                normalized = normalized[: -len(suffix)]
                break

        return normalized

    @staticmethod
    def _is_place_alias_match(left: str | None, right: str | None) -> bool:
        """判斷兩個已正規化的地點別名是否可視為同一地點。

        這裡允許「綠舞」這種短簡稱，但避免「渡假村」「博物館」
        這類泛稱單獨通過比對。
        """
        left = (left or "").strip()
        right = (right or "").strip()

        if not left or not right:
            return False

        generic_only_words = {
            "渡假村",
            "度假村",
            "飯店",
            "酒店",
            "旅館",
            "旅店",
            "園區",
            "中心",
            "展館",
            "藝館",
            "美術館",
            "博物館",
            "老街",
            "夜市",
            "車站",
            "餐廳",
            "遊戲室",
            "浴場",
            "泳池",
            "咖啡",
            "cafe",
            "廳",
            "館",
        }
        if left in generic_only_words or right in generic_only_words:
            return False

        if left == right:
            return True

        if len(left) >= 2 and len(right) >= 2:
            return left in right or right in left

        return False

    @classmethod
    def _extract_requested_place_hint(cls, question: str | None) -> str | None:
        """從追問中抽出使用者疑似想切換詢問的地點名稱。

        例：
        - 「介紹台北101」 -> 「台北101」
        - 「請介紹巧藝館」 -> 「巧藝館」
        - 「台北101」 -> 「台北101」

        這個函式只做簡單規則判斷；真正是否允許，會再檢查這個 hint
        是否存在於目前鎖定景點的知識庫內容中。
        """
        question = (question or "").strip()
        if not question:
            return None

        cleaned = re.sub(r"\s+", " ", question).strip(" ，。！？!?,.：:\n\t")

        # 代名詞型追問，代表仍在問目前鎖定地點。
        generic_targets = {
            "這裡", "這邊", "此地", "這個地方", "這個景點", "這個館", "這個園區",
            "它", "他", "此處", "目前地點", "這裡的特色", "這邊的特色",
        }
        if cls._normalize_text_for_compare(cleaned) in {
            cls._normalize_text_for_compare(item) for item in generic_targets
        }:
            return None

        intro_patterns = [
            r"^(?:請|麻煩|幫我|可以)?(?:介紹|說明|導覽|講解|查詢|搜尋|告訴我|我想了解|我要了解)(?:一下|一下子)?(?:關於)?(?P<hint>.+)$",
            r"^請問(?P<hint>.+?)(?:在哪裡|怎麼去|開放時間|營業時間|門票|票價|特色|適合|是什麼).*$",
            r"^(?:what is|tell me about|introduce|please introduce)\s+(?P<hint>.+)$",
        ]

        for pattern in intro_patterns:
            match = re.match(pattern, cleaned, flags=re.IGNORECASE)
            if match:
                hint = (match.group("hint") or "").strip(" ，。！？!?,.：:\n\t")
                hint = re.sub(r"^(一下|關於|有關|這個|這裡的)", "", hint).strip()
                hint = re.sub(r"(的特色|的介紹|的資訊|的資料)$", "", hint).strip()
                if len(cls._normalize_text_for_compare(hint)) >= 2:
                    return hint

        # 使用者只輸入一個短地點名，例如「台北101」。
        # 避免把「門票多少」「怎麼去」這種一般追問誤判為地點。
        followup_words = [
            "門票", "票價", "開放", "營業", "時間", "交通", "怎麼", "如何", "在哪",
            "特色", "適合", "費用", "價格", "照片", "圖片", "推薦", "附近", "餐廳",
            "廁所", "停車", "有什麼", "可以", "多久", "幾點", "為什麼", "嗎", "呢",
        ]
        compact = cls._normalize_text_for_compare(cleaned)
        if 2 <= len(compact) <= 24 and not any(word in cleaned for word in followup_words):
            # 有數字、英文，或常見地點尾綴時，比較像地點名稱。
            if re.search(r"[A-Za-z0-9]", cleaned) or re.search(r"(中心|園區|展館|藝館|美術館|博物館|101|老街|夜市|車站|飯店|酒店|餐廳|廳|館)$", cleaned):
                return cleaned

        return None

    def _is_text_related_to_locked_entity(
        self,
        text: str | None,
        entity_id: str,
        place_name: str,
        extra_aliases: list[str] | None = None,
    ) -> bool:
        """判斷一段文字是否看起來屬於目前鎖定地點。

        除了原本的「連續字串包含」比對，也加入簡稱 / 別名容錯：
        例如「綠舞渡假村」「綠舞度假村」「綠舞」都可對應
        「綠舞觀光渡假村」。
        """
        normalized_text = self._normalize_text_for_compare(text)
        normalized_text_alias = self._normalize_place_alias_for_compare(text)

        if not normalized_text:
            return True

        aliases = [place_name, *(extra_aliases or [])]
        for alias in aliases:
            normalized_alias = self._normalize_text_for_compare(alias)

            # 原本的嚴格包含比對保留。
            if normalized_alias and normalized_alias in normalized_text:
                return True

            # 新增：簡稱 / 別名容錯比對。
            normalized_alias_for_compare = self._normalize_place_alias_for_compare(alias)
            if self._is_place_alias_match(normalized_text_alias, normalized_alias_for_compare):
                return True

        # 檢查目前 entity 的 payload/text/source_path 是否包含這個 hint。
        try:
            entity_records = self.vector_db.get_entity_records(entity_id=entity_id, limit=None)
        except Exception:
            entity_records = []

        for record in entity_records:
            haystacks = [
                record.get("entity_id"),
                record.get("name"),
                record.get("title"),
                record.get("category"),
                record.get("source_path"),
                record.get("relative_path"),
                record.get("image_name"),
                record.get("text"),
            ]
            for haystack in haystacks:
                haystack_text = str(haystack or "")

                normalized_haystack = self._normalize_text_for_compare(haystack_text)
                if normalized_text and normalized_text in normalized_haystack:
                    return True

                # 新增：payload / 文字內容也做別名容錯比對。
                normalized_haystack_alias = self._normalize_place_alias_for_compare(haystack_text)
                if self._is_place_alias_match(normalized_text_alias, normalized_haystack_alias):
                    return True

        return False

    def _detect_unrelated_followup(
        self,
        entity_id: str,
        place_name: str,
        user_question: str,
        attraction_title: str | None = None,
    ) -> dict[str, Any]:
        """判斷追問是否明顯想切換到其他地點。

        回傳：
        {
            "is_unrelated": bool,
            "requested_place": str,
            "reason": str,
        }
        """
        question = (user_question or "").strip()
        if not question:
            return {"is_unrelated": False, "requested_place": "", "reason": "empty_question"}

        # 問題本身有提到目前鎖定地點，視為相關。
        if self._is_text_related_to_locked_entity(
            text=question,
            entity_id=entity_id,
            place_name=place_name,
            extra_aliases=[attraction_title or ""],
        ):
            return {"is_unrelated": False, "requested_place": "", "reason": "mentions_locked_entity"}

        requested_place = self._extract_requested_place_hint(question)
        if requested_place:
            # 例如「請介紹巧藝館」若巧藝館存在於國立傳統藝術中心的資料中，仍允許回答。
            if self._is_text_related_to_locked_entity(
                text=requested_place,
                entity_id=entity_id,
                place_name=place_name,
                extra_aliases=[attraction_title or ""],
            ):
                return {"is_unrelated": False, "requested_place": requested_place, "reason": "hint_inside_locked_entity"}

            return {
                "is_unrelated": True,
                "requested_place": requested_place,
                "reason": "explicit_other_place_hint",
            }

        # 沒有明確地點詞時，避免過度阻擋一般追問，例如「門票多少」「怎麼去」。
        return {"is_unrelated": False, "requested_place": "", "reason": "no_place_hint"}

    def _build_unrelated_followup_answer(
        self,
        locked_place_name: str,
        requested_place: str,
        target_language: str = "zh-TW",
    ) -> str:
        target_language = self._normalize_language_code(target_language)
        requested_text = requested_place or "其他地點"

        if target_language == "en-US":
            return (
                f"This conversation is currently focused on “{locked_place_name}”. "
                f"Your new question appears to be about “{requested_text}”, which is a different place. "
                "Please start a new guide search or upload a photo of that place, so I can identify it and provide the correct guide information."
            )

        if target_language == "ja-JP":
            return (
                f"現在の案内対象は「{locked_place_name}」です。"
                f"今回の質問は「{requested_text}」という別の場所についての内容のようです。"
                "その場所の写真をアップロードするか、新しく検索してから質問してください。"
            )

        if target_language == "ko-KR":
            return (
                f"현재 안내 대상은 「{locked_place_name}」입니다. "
                f"이번 질문은 「{requested_text}」라는 다른 장소에 대한 내용으로 보입니다. "
                "해당 장소의 사진을 업로드하거나 새로 검색한 뒤 질문해 주세요."
            )

        return (
            f"目前這段導覽已鎖定在「{locked_place_name}」。\n\n"
            f"您剛剛詢問的「{requested_text}」看起來是另一個地點，"
            "為了避免把不同景點的資料混在一起，我先不直接回答。\n\n"
            "請重新上傳該地點照片，或回到專屬導遊重新搜尋該地點；"
            f"如果要繼續詢問「{locked_place_name}」，可以問它的特色、交通、開放時間或適合族群。"
        )

    def _build_unrelated_followup_result(
        self,
        entity_id: str,
        place_name: str,
        scope: str,
        category: str,
        requested_place: str,
        target_language: str,
    ) -> dict[str, Any]:
        representative_image_paths = self._get_representative_image_paths(
            entity_id=entity_id,
            base_records=[],
            limit=12,
        )
        return {
            "place_id": entity_id,
            "place_name": place_name,
            "display_title": place_name,
            "display_subtitle": category or scope or "",
            "scope": scope,
            "category": category,
            "answer": self._build_unrelated_followup_answer(
                locked_place_name=place_name,
                requested_place=requested_place,
                target_language=target_language,
            ),
            "representative_image_path": representative_image_paths[0] if representative_image_paths else None,
            "representative_image_paths": representative_image_paths,
            "evidence_chunks": [],
            "notes": ["偵測到使用者追問可能是另一個地點，因此拒絕混用目前鎖定景點資料。"],
            "is_off_topic_followup": True,
            "requested_place": requested_place,
        }

    @staticmethod
    def _is_supported_image_path(path: str | Path) -> bool:
        return Path(str(path)).suffix.lower() in IMAGE_EXTENSIONS

    def _image_sort_key(self, image_path: Path) -> tuple[int, int, str]:
        stem = image_path.stem.lower()
        suffix = image_path.suffix.lower()
        keyword_score = 0 if any(keyword in stem for keyword in IMAGE_PRIORITY_KEYWORDS) else 1
        extension_score_map = {
            ".heic": 0,
            ".heif": 0,
            ".jpg": 1,
            ".jpeg": 1,
            ".png": 2,
            ".webp": 3,
            ".bmp": 4,
            ".gif": 5,
            ".tif": 6,
            ".tiff": 6,
        }
        return keyword_score, extension_score_map.get(suffix, 99), image_path.name.lower()

    def _candidate_image_dirs_from_records(self, records: list[dict[str, Any]]) -> list[Path]:
        candidate_dirs: list[Path] = []
        seen: set[str] = set()

        def add_dir(path: Path):
            key = str(path.resolve()) if path.exists() else str(path)
            if key not in seen:
                candidate_dirs.append(path)
                seen.add(key)

        for record in records:
            source_path = record.get("source_path")
            if not source_path:
                continue

            path = self._project_path(source_path)
            parent = path.parent

            if self._is_supported_image_path(path):
                add_dir(parent)
                if parent.name.lower() == "images":
                    add_dir(parent.parent)
                else:
                    add_dir(parent / "images")
                continue

            if parent.name.lower() == "documents":
                add_dir(parent.parent / "images")
                add_dir(parent.parent)
            else:
                add_dir(parent / "images")
                add_dir(parent)

        return candidate_dirs

    def _find_images_in_dirs(self, image_dirs: list[Path], limit: int = 12) -> list[str]:
        found_images: list[Path] = []
        seen: set[str] = set()

        for image_dir in image_dirs:
            if not image_dir.is_dir():
                continue

            for image_path in image_dir.rglob("*"):
                if not image_path.is_file():
                    continue
                if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue

                key = str(image_path.resolve())
                if key in seen:
                    continue

                found_images.append(image_path)
                seen.add(key)

        found_images = sorted(found_images, key=self._image_sort_key)
        return [self._to_project_relative_path(image_path) for image_path in found_images[:limit]]

    @staticmethod
    def _merge_unique_paths(paths: list[str | None], limit: int = 12) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()

        for path in paths:
            if not path:
                continue

            normalized = str(path).replace("\\", "/")
            if normalized in seen:
                continue

            merged.append(normalized)
            seen.add(normalized)

            if len(merged) >= limit:
                break

        return merged

    def _get_representative_image_paths(
        self,
        entity_id: str,
        base_records: list[dict[str, Any]] | None = None,
        current_paths: list[str] | None = None,
        limit: int = 12,
    ) -> list[str]:
        """
        取得代表圖片候選清單。

        Qdrant / Azure Blob 模式重點：
        - 圖片來源以 Qdrant payload 的 source_path 為準。
        - source_path 對應 Azure Blob name，例如 data/raw/RAG知識庫/.../images/main.JPG。
        - 不再掃描本機 data/raw，也不使用使用者上傳圖片當代表圖。
        """
        base_records = base_records or []
        current_paths = current_paths or []

        image_records = self.vector_db.get_representative_image_records(
            entity_id=entity_id,
            limit=limit * 3,
        )

        candidate_paths = self._merge_unique_paths(
            [
                *current_paths,
                *[
                    record.get("source_path")
                    for record in image_records
                    if record.get("source_path")
                ],
                *[
                    record.get("source_path")
                    for record in base_records
                    if record.get("modality") == "image" and record.get("source_path")
                ],
            ],
            limit=limit * 5,
        )

        supported_paths = [
            path
            for path in candidate_paths
            if self._is_supported_image_path(path)
        ]

        sorted_paths = sorted(
            supported_paths,
            key=lambda path: self._image_sort_key(Path(str(path))),
        )
        return sorted_paths[:limit]

    @staticmethod
    def _extract_display_titles_from_source_path(source_path: str | None) -> dict[str, str]:
        if not source_path:
            return {"display_title": "", "display_subtitle": ""}

        normalized_path = str(source_path).replace("\\", "/")
        filename = normalized_path.split("/")[-1].strip()
        if not filename:
            return {"display_title": "", "display_subtitle": ""}

        filename_without_ext = Path(filename).stem.strip()
        if not filename_without_ext:
            return {"display_title": "", "display_subtitle": ""}

        dash_parts = [
            part.strip()
            for part in re.split(r"[-－—]", filename_without_ext)
            if part.strip()
        ]
        last_part = dash_parts[-1] if dash_parts else filename_without_ext

        if "_" in last_part:
            subtitle, title = last_part.rsplit("_", 1)
            return {"display_title": title.strip(), "display_subtitle": subtitle.strip()}

        if "＿" in last_part:
            subtitle, title = last_part.rsplit("＿", 1)
            return {"display_title": title.strip(), "display_subtitle": subtitle.strip()}

        return {
            "display_title": last_part.strip(),
            "display_subtitle": dash_parts[-2].strip() if len(dash_parts) >= 2 else "",
        }

    def _get_display_titles_from_records(
        self,
        records: list[dict[str, Any]],
        fallback_title: str = "",
    ) -> dict[str, str]:
        for record in records:
            if record.get("modality") != "text":
                continue

            source_path = record.get("source_path")
            if not source_path:
                continue

            display_info = self._extract_display_titles_from_source_path(source_path)
            if display_info.get("display_title") or display_info.get("display_subtitle"):
                return {
                    "display_title": display_info.get("display_title") or fallback_title,
                    "display_subtitle": display_info.get("display_subtitle") or "",
                }

        return {"display_title": fallback_title or "", "display_subtitle": ""}

    def _extract_text_from_uploaded_document(self, path: Path) -> str:
        if not path.exists():
            return ""

        suffix = path.suffix.lower()
        if suffix in [".txt", ".md", ".csv", ".json"]:
            try:
                return path.read_text(encoding="utf-8", errors="ignore")[:3000]
            except Exception:
                return ""

        if suffix == ".pdf":
            try:
                reader = PdfReader(str(path))
                texts = []
                for page in reader.pages[:3]:
                    text = page.extract_text() or ""
                    if text.strip():
                        texts.append(text.strip())
                return "\n".join(texts)[:3000]
            except Exception:
                return ""

        return ""

    def _collect_query_vectors(
        self,
        user_input: str,
        input_items: list[dict[str, Any]],
    ) -> tuple[list[Any], list[str]]:
        """
        收集本次查詢向量。

        重要：使用者上傳圖片只在記憶體中讀成 bytes 產生 embedding，
        不再寫入 uploads，也不再使用 saved_path。
        """
        query_vectors = []
        notes = []

        if user_input:
            query_vectors.append(self._embed_query_text(user_input))

        for item in input_items:
            kind = item.get("kind")

            if kind == "image":
                try:
                    image_bytes = item.get("bytes") or b""
                    if not image_bytes:
                        notes.append(f"圖片內容為空：{item.get('original_name')}")
                        continue

                    if not hasattr(self.embedding_model, "embed_image_bytes"):
                        notes.append("目前 embedding model 不支援圖片 bytes embedding。")
                        continue

                    query_vectors.append(
                        self.embedding_model.embed_image_bytes(
                            image_bytes=image_bytes,
                            mime_type=item.get("mime_type"),
                            filename=item.get("original_name"),
                        )
                    )
                except Exception as e:
                    notes.append(f"圖片無法建立 embedding：{item.get('original_name')}，原因：{e}")

        return query_vectors, notes

    def _search_all_vectors(self, query_vectors: list[Any]) -> list[dict[str, Any]]:
        all_results = []
        for vector in query_vectors:
            results = self.vector_db.search(
                query_vector=vector,
                top_k=3,    # 這裡 top_k=3 是每個向量取前 3 筆結果，避免一次取太多造成資料重複或不必要的計算
                fetch_k=80, # 增加 fetch_k 以取得更多候選結果(80筆)，避免因 top_k 過小而漏掉相關資料
            )
            all_results.extend(results)
        return all_results

    def _get_evidence_texts(
        self,
        entity_id: str,
        query: str | None = None,
        top_k: int = 6,
    ) -> list[dict[str, Any]]:
        if query:
            vector = self._embed_query_text(query)
            results = self.vector_db.search(
                query_vector=vector,
                top_k=top_k,
                filters={"entity_id": entity_id, "modality": "text"},
                fetch_k=120,
            )
            if results:
                return results

        return self.vector_db.get_entity_records(
            entity_id=entity_id,
            modality="text",
            limit=top_k,
        )

    @staticmethod
    def _build_context_text(evidence_records: list[dict[str, Any]]) -> str:
        context_parts = []
        for idx, record in enumerate(evidence_records, start=1):
            text = (record.get("text") or "").strip()
            if not text:
                continue

            context_parts.append(
                f"[資料{idx}] "
                f"地點：{record.get('name', '')}；"
                f"分類：{record.get('category', '')}；"
                f"頁碼：{record.get('page', 'N/A')}\n"
                f"{text}"
            )
        return "\n\n".join(context_parts)

    def _generate_answer(
        self,
        place_name: str,
        scope: str,
        category: str,
        question: str,
        context_text: str,
        target_language: str = "zh-TW",
        extra_notes: list[str] | None = None,
    ) -> str:
        notes_text = "\n".join(extra_notes or [])
        target_language = self._normalize_language_code(target_language)
        language_instruction = self._language_instruction(target_language)

        prompt = build_guide_answer_prompt(
            place_name=place_name,
            scope=scope,
            category=category,
            question=question,
            context_text=context_text,
            target_language=target_language,
            language_instruction=language_instruction,
            notes_text=notes_text,
        )


        try:
            answer = self._call_llm_with_retry(prompt)
            if answer:
                return answer.strip()
        except Exception as e:
            print(f"[GUIDE LLM ERROR] {e}")

        return self._build_fallback_answer(
            place_name=place_name,
            scope=scope,
            category=category,
            context_text=context_text,
            target_language=target_language,
        )

    def _call_llm_once(self, prompt: str) -> str:
        if self.model_provider == "azure":
            response = self.llm_client.responses.create(
                model=self.generation_model,
                input=prompt,
                store=False,
            )

            answer = getattr(response, "output_text", None)
            return answer.strip() if answer else ""

        response = self.llm_client.models.generate_content(
            model=self.generation_model,
            contents=prompt,
        )

        answer = getattr(response, "text", None)
        return answer.strip() if answer else ""

    def _call_llm_with_retry(self, prompt: str, max_retries: int = 2) -> str:
        """呼叫 Gemini 生成導覽文字。

        Gemini 偶爾會回 503 high demand，因此這裡做簡單重試。
        若最後仍失敗，由 _build_fallback_answer() 回傳短版備援文字，
        避免把整段 raw chunks 直接塞到前端畫面。
        """
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                return self._call_llm_once(prompt)
            except Exception as e:
                last_error = e
                print(f"[GUIDE LLM RETRY] attempt={attempt}, error={e}")
                if attempt < max_retries:
                    time.sleep(1.5 * attempt)

        if last_error:
            raise last_error

        return ""

    @staticmethod
    def _compact_context_excerpt(context_text: str, max_chars: int = 260) -> str:
        """把知識庫內容縮成前端可閱讀的短摘要。"""
        if not context_text:
            return ""

        # 移除 [資料1]、地點、分類、頁碼等檢索標記，避免前端顯示太像 debug 資料。
        cleaned = re.sub(r"\[資料\d+\]\s*", "", context_text)
        cleaned = re.sub(r"地點：.*?\n", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if len(cleaned) > max_chars:
            cleaned = cleaned[:max_chars].rstrip() + "..."

        return cleaned

    def _build_fallback_answer(
        self,
        place_name: str,
        scope: str,
        category: str,
        context_text: str,
        target_language: str = "zh-TW",
    ) -> str:
        """LLM 忙碌或失敗時的短版回答。

        重點：
        1. 不回傳完整 context_text，避免畫面出現 raw chunks。
        2. 仍盡量使用 target_language，避免英文 / 日文問題回成中文。
        """
        target_language = self._normalize_language_code(target_language)
        excerpt = self._compact_context_excerpt(context_text)
        location_text = category or scope or "園區內景點"

        if target_language == "en-US":
            return (
                f"I found information for “{place_name}”.\n\n"
                "The AI guide-writing service is temporarily busy, "
                "so I cannot generate a fully polished answer right now. "
                "Please try again shortly, or ask about this place’s features, opening hours, transportation, or suitability for families."
            )

        if target_language == "ja-JP":
            return (
                f"「{place_name}」に関する情報が見つかりました。\n\n"
                "現在、AIガイド文の生成サービスが一時的に混み合っています。"
                "少し時間をおいて再度お試しください。"
                "この場所の特色、営業時間、アクセス、家族向けかどうかについて続けて質問できます。"
            )

        if target_language == "ko-KR":
            return (
                f"「{place_name}」에 대한 정보를 찾았습니다.\n\n"
                "현재 AI 안내문 생성 서비스가 일시적으로 혼잡합니다. "
                "잠시 후 다시 시도해 주세요. 이 장소의 특징, 운영 시간, 교통편, 가족 여행 적합성 등을 이어서 질문하실 수 있습니다."
            )

        if excerpt:
            return (
                f"目前已辨識到地點為「{place_name}」。\n\n"
                f"這裡屬於「{location_text}」。"
                f"目前 AI 導覽文字整理服務暫時忙碌，先提供簡短介紹：{excerpt}\n\n"
                "您也可以繼續詢問這個地點的特色、開放時間、交通方式或適合族群。"
            )

        return (
            f"目前已辨識到地點為「{place_name}」。\n\n"
            "但目前知識庫資料不足，暫時無法提供更完整介紹。"
        )

    def _build_result_for_entity(
        self,
        entity_id: str,
        place_name: str,
        scope: str,
        category: str,
        question: str,
        target_language: str = "zh-TW",
        notes: list[str] | None = None,
    ) -> dict[str, Any]:
        evidence_records = self._get_evidence_texts(
            entity_id=entity_id,
            query=question or place_name,
            top_k=6,
        )
        display_info = self._get_display_titles_from_records(
            records=evidence_records,
            fallback_title=place_name,
        )
        context_text = self._build_context_text(evidence_records)
        answer = self._generate_answer(
            place_name=place_name,
            scope=scope,
            category=category,
            question=question or f"請介紹 {place_name}",
            context_text=context_text,
            target_language=target_language,
            extra_notes=notes,
        )

        representative_image_paths = self._get_representative_image_paths(
            entity_id=entity_id,
            base_records=evidence_records,
            limit=12,
        )

        return {
            "place_id": entity_id,
            "place_name": place_name,
            "display_title": display_info.get("display_title") or place_name,
            "display_subtitle": display_info.get("display_subtitle") or "",
            "scope": scope,
            "category": category,
            "answer": answer,
            "representative_image_path": representative_image_paths[0] if representative_image_paths else None,
            "representative_image_paths": representative_image_paths,
            "evidence_chunks": evidence_records,
        }

    def recognize_place(
        self,
        user_input: str,
        input_items: list[dict[str, Any]],
        target_language: str = "zh-TW",
    ) -> dict[str, Any]:
        query_vectors, notes = self._collect_query_vectors(user_input, input_items)

        if not query_vectors:
            raise ValueError("沒有可用來查詢的文字或圖片。請輸入文字或上傳圖片。")

        all_results = self._search_all_vectors(query_vectors)
        entities = self.vector_db.aggregate_by_entity(all_results)

        if not entities:
            raise ValueError("向量資料庫沒有找到相似地點。")

        best_entity = entities[0]
        entity_id = best_entity["entity_id"]
        place_name = best_entity.get("place_name") or "未知地點"
        scope = best_entity.get("scope") or ""
        category = best_entity.get("category") or ""
        best_score = float(best_entity.get("best_score", 0.0))

        # 首頁第一次查詢時，Qdrant 一定會回傳「最相近」的資料，
        # 但「最相近」不代表「真的相關」。
        # 因此：
        # 1. 先用最低信心門檻擋掉低分結果。
        # 2. 若使用者明確指定一個地點，但該地點不屬於命中的 entity，
        #    就判定為知識庫外或非相關地點，避免硬推其他景點。
        # 圖片查詢仍以向量辨識為主；文字查詢才啟用明確地點防呆。
        has_image_input = any(item.get("kind") == "image" for item in input_items)
        is_text_only_query = bool((user_input or "").strip()) and not has_image_input
        score_threshold = float(0.70)   # 最低信心門檻，低於此分數就不認為是相關景點。

        if best_score < score_threshold:
            raise ValueError(
                "沒有在專屬導遊知識庫中找到足夠相關的景點。"
                "請改用渡假村內景點、周邊景點名稱，或上傳景點照片重新辨識。"
            )

        if is_text_only_query:
            requested_place = self._extract_requested_place_hint(user_input)
            if requested_place and not self._is_text_related_to_locked_entity(
                text=requested_place,
                entity_id=entity_id,
                place_name=place_name,
                extra_aliases=[category, scope],
            ):
                raise ValueError(
                    f"目前專屬導遊知識庫沒有找到與「{requested_place}」足夠相關的景點資料。"
                    "請輸入渡假村內景點、周邊景點名稱，或上傳該地點照片重新辨識。"
                )

        question = user_input or f"使用者提供圖片資料，請介紹最可能的地點：{place_name}。"
        result = self._build_result_for_entity(
            entity_id=entity_id,
            place_name=place_name,
            scope=scope,
            category=category,
            question=question,
            target_language=target_language,
            notes=notes,
        )

        result.update(
            {
                "confidence_score": float(best_entity.get("best_score", 0.0)),
                "matched_entities": entities[:5],
                "notes": notes,
            }
        )

        # 不再使用使用者上傳圖片當代表圖，避免保存或回傳使用者上傳資料。

        return result

    def answer_followup(
        self,
        attraction_title: str,
        user_question: str,
        target_language: str = "zh-TW",
    ) -> dict[str, Any]:
        matched_record = self.vector_db.find_entity_by_title(attraction_title)

        if not matched_record:
            # 找不到鎖定地點時，退回一般查詢，但把 attraction_title 放進查詢文字。
            return self.recognize_place(
                user_input=f"{attraction_title}\n{user_question}",
                input_items=[],
                target_language=target_language,
            )

        entity_id = matched_record.get("entity_id")
        place_name = matched_record.get("name") or matched_record.get("title") or attraction_title
        scope = matched_record.get("scope") or ""
        category = matched_record.get("category") or ""

        # 追問時先判斷使用者是否明顯切換到另一個地點。
        # 例如目前鎖定「國立傳統藝術中心」，但使用者問「介紹台北101」，
        # 就不要強迫 LLM 用國立傳統藝術中心的資料回答。
        unrelated_info = self._detect_unrelated_followup(
            entity_id=entity_id,
            place_name=place_name,
            user_question=user_question,
            attraction_title=attraction_title,
        )
        if unrelated_info.get("is_unrelated"):
            return self._build_unrelated_followup_result(
                entity_id=entity_id,
                place_name=place_name,
                scope=scope,
                category=category,
                requested_place=unrelated_info.get("requested_place") or user_question,
                target_language=target_language,
            )

        return self._build_result_for_entity(
            entity_id=entity_id,
            place_name=place_name,
            scope=scope,
            category=category,
            question=user_question,
            target_language=target_language,
            notes=[f"本次為使用者針對「{attraction_title}」的後續追問。"],
        )


class GuideService:
    def __init__(self):
        # 延遲載入核心服務，避免 uvicorn 啟動時就初始化 Qdrant / Gemini。
        # 只有真正呼叫 /api/guide/analyze 時才建立 GuideCoreService。
        self._core: GuideCoreService | None = None

    @property
    def core(self) -> GuideCoreService:
        if self._core is None:
            self._core = GuideCoreService()
        return self._core

    @staticmethod
    def _compose_guide_message(answer: str, user_name: str | None) -> str:
        answer = (answer or "").strip()
        if not answer:
            answer = "已完成專屬導遊分析。"
        user_name = (user_name or "").strip()
        if (
            user_name
            and user_name not in ["貴賓", "Guest"]
            and not answer.startswith(user_name)
        ):
            return f"{user_name}，{answer}"
        return answer

    async def analyze(
        self,
        language: str,
        image: UploadFile | None = None,
        text: str | None = None,
        voice: UploadFile | None = None,
        attraction_title: str | None = None,
        user_name: str | None = None,
        history: str | None = None,
        db: Any | None = None,
        current_user: Any | None = None,
    ) -> dict:
        input_items: list[dict[str, Any]] = []
        user_text = ""
        
        try:
            if voice:
                print(f"[GUIDE VOICE] filename={voice.filename}, content_type={voice.content_type}")
                # stt_result = await guide_speech_to_text_service.transcribe_upload_file(voice)

                stt_result = await speech_to_text_service.transcribe_upload_file(voice)



                print(f"[GUIDE VOICE] STT result={stt_result}")
                user_text = (stt_result or {}).get("text", "") or ""

                if not user_text.strip():
                    stt_error = (stt_result or {}).get("error") or "語音沒有成功轉成文字。"
                    raise ValueError(f"語音輸入失敗：{stt_error}")

            query_parts = []
            if text and text.strip():
                query_parts.append(text.strip())
            if user_text and user_text.strip() and not user_text.startswith(("系統錯誤", "辨識取消", "無法辨識", "沒有收到")):
                query_parts.append(user_text.strip())

            query_text = "\n".join(query_parts).strip()

            # 以使用者本次輸入為準決定回答語言；若只有圖片沒有文字，才使用前端 UI 語言當 fallback。
            target_language = self.core._detect_language_from_text(
                query_text,
                fallback=language or "zh-TW",
            )

            if image and image.filename:
                image_bytes = await image.read()
                if image_bytes:
                    input_items.append(
                        {
                            "label": "上傳圖片",
                            "original_name": image.filename,
                            "mime_type": image.content_type or "application/octet-stream",
                            "kind": "image",
                            "bytes": image_bytes,
                        }
                    )

            if attraction_title and query_text and not image:
                place_result = self.core.answer_followup(
                    attraction_title=attraction_title,
                    user_question=query_text,
                    target_language=target_language,
                )
            else:
                place_result = self.core.recognize_place(
                    user_input=query_text,
                    input_items=input_items,
                    target_language=target_language,
                )

            place_result = guide_image_service.attach_representative_image_url(place_result)

            title = (
                place_result.get("display_title")
                or place_result.get("place_name")
                or attraction_title
                or "專屬導遊"
            )
            location = (
                place_result.get("display_subtitle")
                or place_result.get("category")
                or place_result.get("scope")
                or ""
            )
            answer = place_result.get("answer") or "已完成專屬導遊分析。"

            guide_message = self._compose_guide_message(answer, user_name)
            guide_message_text = markdown_to_text(guide_message).strip()

            audio_base64 = get_gemini_tts_service().synthesize_base64(
                text=guide_message_text,
                language=target_language,
            )


            return {
                "success": True,
                "title": title,
                "location": location,

                # 給前端畫面顯示，保留 Markdown
                "guideMessage": guide_message,

                # 給 TTS 語音使用，移除 Markdown 符號
                "guideMessageText": guide_message_text,

                "audioUrl": "",
                "imageUrl": place_result.get("representative_image_url") or "",
                "user_text": user_text,
                "responseLanguage": target_language,
                "audio_base64": audio_base64
            }

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except FileNotFoundError as e:
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"專屬導遊分析失敗：{str(e)}")


@lru_cache
def get_guide_service() -> GuideService:
    return GuideService()


# 給 app.api.guide_router 使用：
# from app.services.guide_service import guide_service
#
# 注意：GuideService 內部採延遲載入，因此這行不會在啟動時直接連線 Qdrant。
guide_service = get_guide_service()
