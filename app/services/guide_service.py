import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from pypdf import PdfReader

from app.core.config import settings
from app.services.guide_embedding_service import get_guide_embedding_model
from app.services.guide_file_service import guide_file_service
from app.services.guide_image_service import guide_image_service
from app.services.guide_model_service import get_guide_model
from app.services.guide_vector_db_service import GuideVectorDBService
from app.services.speech_to_text_service import speech_to_text_service


IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".heic", ".heif",
}

IMAGE_PRIORITY_KEYWORDS = ["main", "cover", "thumbnail", "thumb", "代表", "封面", "主要"]


class GuideCoreService:
    """
    專屬導遊核心邏輯。

    這份是從新人 Flask 專案 personal_tour_guide.py 拆出來的 FastAPI 版，
    並保留原本 data/ 架構與 metadata source_path。
    """

    def __init__(self):
        self.embedding_model = get_guide_embedding_model()
        self.vector_db = GuideVectorDBService()
        self.llm_client = get_guide_model()
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
        base_records = base_records or []
        current_paths = current_paths or []

        image_records = self.vector_db.get_representative_image_records(
            entity_id=entity_id,
            limit=limit * 3,
        )

        vector_image_paths = [
            record.get("source_path")
            for record in image_records
            if record.get("source_path")
        ]

        all_entity_records = self.vector_db.get_entity_records(entity_id=entity_id)
        candidate_dirs = self._candidate_image_dirs_from_records(
            [*base_records, *image_records, *all_entity_records]
        )
        scanned_image_paths = self._find_images_in_dirs(candidate_dirs, limit=limit * 5)

        combined_paths = self._merge_unique_paths(
            [*current_paths, *vector_image_paths, *scanned_image_paths],
            limit=limit * 10,
        )

        existing_image_paths: list[Path] = []
        seen: set[str] = set()

        for path in combined_paths:
            path_obj = self._project_path(path)
            if not path_obj.is_file():
                continue
            if path_obj.suffix.lower() not in IMAGE_EXTENSIONS:
                continue

            key = str(path_obj.resolve())
            if key in seen:
                continue

            existing_image_paths.append(path_obj)
            seen.add(key)

        sorted_image_paths = sorted(existing_image_paths, key=self._image_sort_key)
        return [self._to_project_relative_path(image_path) for image_path in sorted_image_paths[:limit]]

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
        query_vectors = []
        notes = []

        if user_input:
            query_vectors.append(self._embed_query_text(user_input))

        for item in input_items:
            kind = item.get("kind")
            saved_path = item.get("saved_path")
            if not saved_path:
                continue

            path = self._project_path(saved_path)

            if kind == "image":
                try:
                    query_vectors.append(self.embedding_model.embed_image_file(path))
                except Exception as e:
                    notes.append(f"圖片無法建立 embedding：{item.get('original_name')}，原因：{e}")

            elif kind == "file":
                extracted_text = self._extract_text_from_uploaded_document(path)
                if extracted_text:
                    query_vectors.append(self._embed_query_text(extracted_text))
                else:
                    notes.append(f"檔案目前未解析或無可抽取文字：{item.get('original_name')}")

        return query_vectors, notes

    def _search_all_vectors(self, query_vectors: list[Any]) -> list[dict[str, Any]]:
        all_results = []
        for vector in query_vectors:
            results = self.vector_db.search(
                query_vector=vector,
                top_k=settings.GUIDE_TOP_K,
                fetch_k=settings.GUIDE_FETCH_K,
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
        extra_notes: list[str] | None = None,
    ) -> str:
        notes_text = "\n".join(extra_notes or [])
        prompt = f"""
你是旅遊渡假村的專屬導遊。
請根據提供的知識庫資料回答使用者問題。

規則：
1. 只能回答「{place_name}」這個地點相關內容。
2. 不要把問題改成其他景點，也不要推薦無關地點。
3. 如果資料不足，請明確說「目前知識庫資料不足」，再用保守方式回答。
4. 回答請使用繁體中文。
5. 回答要簡單、自然、像導遊介紹，適合放在網頁上，字數不超過 200 個字。

目前鎖定地點：
- 地點名稱：{place_name}
- 範圍：{scope}
- 分類：{category}

使用者問題：
{question}

系統補充：
{notes_text}

知識庫資料：
{context_text}
""".strip()

        try:
            response = self.llm_client.models.generate_content(
                model=self.generation_model,
                contents=prompt,
            )
            answer = getattr(response, "text", None)
            if answer:
                return answer.strip()
        except Exception as e:
            print(f"[GUIDE LLM ERROR] {e}")

        if context_text:
            return (
                f"目前已辨識到地點為「{place_name}」。\n\n"
                f"以下是知識庫相關內容摘要：\n{context_text[:1200]}"
            )

        return f"目前已辨識到地點為「{place_name}」，但知識庫資料不足，暫時無法提供更完整介紹。"

    def _build_result_for_entity(
        self,
        entity_id: str,
        place_name: str,
        scope: str,
        category: str,
        question: str,
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

    def recognize_place(self, user_input: str, input_items: list[dict[str, Any]]) -> dict[str, Any]:
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

        question = user_input or f"使用者提供圖片資料，請介紹最可能的地點：{place_name}。"
        result = self._build_result_for_entity(
            entity_id=entity_id,
            place_name=place_name,
            scope=scope,
            category=category,
            question=question,
            notes=notes,
        )

        result.update(
            {
                "confidence_score": float(best_entity.get("best_score", 0.0)),
                "matched_entities": entities[:5],
                "notes": notes,
            }
        )

        # 如果知識庫沒有圖片，就使用使用者上傳圖片當代表圖。
        if not result.get("representative_image_path"):
            for item in input_items:
                if item.get("kind") == "image" and item.get("saved_path"):
                    result["representative_image_path"] = item["saved_path"]
                    result["representative_image_paths"] = [item["saved_path"]]
                    break

        return result

    def answer_followup(self, attraction_title: str, user_question: str) -> dict[str, Any]:
        matched_record = self.vector_db.find_entity_by_title(attraction_title)

        if not matched_record:
            # 找不到鎖定地點時，退回一般查詢，但把 attraction_title 放進查詢文字。
            return self.recognize_place(
                user_input=f"{attraction_title}\n{user_question}",
                input_items=[],
            )

        entity_id = matched_record.get("entity_id")
        place_name = matched_record.get("name") or matched_record.get("title") or attraction_title
        scope = matched_record.get("scope") or ""
        category = matched_record.get("category") or ""

        return self._build_result_for_entity(
            entity_id=entity_id,
            place_name=place_name,
            scope=scope,
            category=category,
            question=user_question,
            notes=[f"本次為使用者針對「{attraction_title}」的後續追問。"],
        )


class GuideService:
    def __init__(self):
        self.core = GuideCoreService()

    @staticmethod
    def _compose_guide_message(answer: str, user_name: str | None) -> str:
        user_name = (user_name or "").strip()
        if user_name and user_name not in ["貴賓", "Guest"] and not answer.startswith(user_name):
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
    ) -> dict:
        input_items: list[dict[str, Any]] = []
        user_text = ""

        try:
            if voice:
                stt_result = await speech_to_text_service.transcribe_upload_file(voice)
                user_text = (stt_result or {}).get("text", "") or ""

            query_parts = []
            if text and text.strip():
                query_parts.append(text.strip())
            if user_text and user_text.strip() and not user_text.startswith(("系統錯誤", "辨識取消", "無法辨識", "沒有收到")):
                query_parts.append(user_text.strip())

            query_text = "\n".join(query_parts).strip()

            if image:
                saved_image = await guide_file_service.save_upload_file(image, label="上傳圖片")
                if saved_image:
                    input_items.append(saved_image.to_input_item())

            if attraction_title and query_text and not image:
                place_result = self.core.answer_followup(
                    attraction_title=attraction_title,
                    user_question=query_text,
                )
            else:
                place_result = self.core.recognize_place(
                    user_input=query_text,
                    input_items=input_items,
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

            return {
                "success": True,
                "title": title,
                "location": location,
                "guideMessage": self._compose_guide_message(answer, user_name),
                "audioUrl": "",
                "imageUrl": place_result.get("representative_image_url") or "",
                "user_text": user_text,
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
