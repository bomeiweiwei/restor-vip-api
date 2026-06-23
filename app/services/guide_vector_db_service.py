import pickle
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from app.core.config import settings


def l2_normalize_vector(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype="float32").reshape(1, -1)
    norm = np.linalg.norm(vector, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    return vector / norm


class GuideVectorDBService:
    """
    Guide 專用 FAISS 向量資料庫查詢服務。

    重點：保留新人專案原本 data/ 架構，不改 metadata source_path，
    預設讀取：data/vector_db/gemini_embedding_2/resort_knowledge.faiss
    """

    def __init__(
        self,
        vector_db_dir: str | Path | None = None,
        index_filename: str | None = None,
        metadata_filename: str | None = None,
    ):
        project_root = Path(settings.GUIDE_PROJECT_ROOT).resolve()
        vector_db_dir = vector_db_dir or settings.GUIDE_VECTOR_DB_DIR

        vector_db_path = Path(vector_db_dir)
        if not vector_db_path.is_absolute():
            vector_db_path = project_root / vector_db_path

        self.vector_db_dir = vector_db_path.resolve()
        self.index_path = self.vector_db_dir / (index_filename or settings.GUIDE_VECTOR_INDEX_FILE)
        self.metadata_path = self.vector_db_dir / (metadata_filename or settings.GUIDE_VECTOR_METADATA_FILE)

        if not self.index_path.exists():
            raise FileNotFoundError(f"找不到 FAISS index：{self.index_path}")

        if not self.metadata_path.exists():
            raise FileNotFoundError(f"找不到 metadata pkl：{self.metadata_path}")

        self.index = faiss.read_index(str(self.index_path))

        with self.metadata_path.open("rb") as f:
            self.metadata: list[dict[str, Any]] = pickle.load(f)

        if self.index.ntotal != len(self.metadata):
            raise ValueError(
                "FAISS 向量數與 metadata 筆數不一致："
                f"index={self.index.ntotal}, metadata={len(self.metadata)}"
            )

    def _match_filters(self, record: dict[str, Any], filters: dict[str, Any] | None) -> bool:
        if not filters:
            return True

        for key, expected_value in filters.items():
            if expected_value is None:
                continue

            actual_value = record.get(key)

            if isinstance(expected_value, (list, tuple, set)):
                if actual_value not in expected_value:
                    return False
            else:
                if actual_value != expected_value:
                    return False

        return True

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
        fetch_k: int | None = None,
    ) -> list[dict[str, Any]]:
        if self.index.ntotal == 0:
            return []

        top_k = top_k or settings.GUIDE_TOP_K
        query = l2_normalize_vector(query_vector)

        if fetch_k is None:
            fetch_k = min(settings.GUIDE_FETCH_K, self.index.ntotal)
        else:
            fetch_k = min(fetch_k, self.index.ntotal)

        scores, indices = self.index.search(query, fetch_k)

        results: list[dict[str, Any]] = []

        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue

            record = dict(self.metadata[int(idx)])

            if not self._match_filters(record, filters):
                continue

            record["score"] = float(score)
            record["index_id"] = int(idx)
            results.append(record)

            if len(results) >= top_k:
                break

        return results

    def get_entity_records(
        self,
        entity_id: str,
        modality: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        records = []

        for record in self.metadata:
            if record.get("entity_id") != entity_id:
                continue

            if modality and record.get("modality") != modality:
                continue

            records.append(dict(record))

        if limit is not None:
            return records[:limit]

        return records

    def find_entity_by_title(self, title: str) -> dict[str, Any] | None:
        """
        結果頁追問時，前端只會帶 attraction_title。
        這裡嘗試從 metadata 反查對應 entity_id。
        """
        title = (title or "").strip()
        if not title:
            return None

        # 先做精準比對
        for record in self.metadata:
            values = [
                record.get("name"),
                record.get("title"),
            ]
            if title in [str(v).strip() for v in values if v]:
                return dict(record)

        # 再做寬鬆比對，支援 display_title 是從 PDF 檔名解析出來的情境
        for record in self.metadata:
            haystacks = [
                str(record.get("entity_id") or ""),
                str(record.get("source_path") or ""),
                str(record.get("name") or ""),
                str(record.get("title") or ""),
            ]
            if any(title in haystack for haystack in haystacks):
                return dict(record)

        return None

    def _image_sort_key(self, record: dict[str, Any]) -> tuple[int, int, str]:
        image_name = (record.get("image_name") or record.get("source_path") or "").lower()
        suffix = Path(image_name).suffix.lower()

        priority_keywords = [
            "main_", "main", "cover_", "cover", "代表", "封面",
            "thumbnail_", "thumbnail", "thumb_", "thumb", "signboard_",
            "entrance_", "exterior_", "interior_", "scenery_", "feature_", "food_",
        ]

        keyword_priority = 99
        for index, keyword in enumerate(priority_keywords):
            if keyword.lower() in image_name:
                keyword_priority = index
                break

        # HEIC / HEIF 不降權，讓 main.HEIC 可以被選成代表圖。
        ext_priority_map = {
            ".heic": 0,
            ".heif": 0,
            ".jpg": 1,
            ".jpeg": 1,
            ".png": 2,
            ".webp": 3,
            ".bmp": 4,
            ".tif": 5,
            ".tiff": 5,
        }
        ext_priority = ext_priority_map.get(suffix, 9)

        return keyword_priority, ext_priority, image_name

    def get_representative_image_records(
        self,
        entity_id: str,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        image_records = self.get_entity_records(entity_id, modality="image")

        if not image_records:
            return []

        sorted_records = sorted(image_records, key=self._image_sort_key)
        return sorted_records[:limit]

    def aggregate_by_entity(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        entity_map: dict[str, dict[str, Any]] = {}

        for result in results:
            entity_id = result.get("entity_id")
            if not entity_id:
                continue

            if entity_id not in entity_map:
                entity_map[entity_id] = {
                    "entity_id": entity_id,
                    "place_name": result.get("name"),
                    "scope": result.get("scope"),
                    "category": result.get("category"),
                    "best_score": float(result.get("score", 0.0)),
                    "total_score": 0.0,
                    "hit_count": 0,
                    "records": [],
                }

            score = float(result.get("score", 0.0))
            modality = result.get("modality")
            weight = 1.2 if modality == "image" else 1.0

            entity_map[entity_id]["total_score"] += score * weight
            entity_map[entity_id]["best_score"] = max(entity_map[entity_id]["best_score"], score)
            entity_map[entity_id]["hit_count"] += 1
            entity_map[entity_id]["records"].append(result)

        entities = list(entity_map.values())
        entities.sort(
            key=lambda item: (item["total_score"], item["best_score"], item["hit_count"]),
            reverse=True,
        )
        return entities
