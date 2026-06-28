from pathlib import Path
from typing import Any

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from app.core.config import settings


def vector_to_list(vector: np.ndarray | list[float]) -> list[float]:
    """將 Gemini 回傳的 numpy vector 轉成 Qdrant 可接受的 list[float]。"""
    return np.asarray(vector, dtype="float32").reshape(-1).tolist()


class GuideVectorDBService:
    """
    Guide 專用 Qdrant 向量資料庫查詢服務。

    目前正式模式：
    - 使用 GUIDE_QDRANT_URL / GUIDE_QDRANT_API_KEY 連線到 Guide 專用 Qdrant。
    - 查詢 collection：GUIDE_QDRANT_COLLECTION_NAME，預設 resort_guide。
    - Qdrant point payload 保留原本 metadata 結構，例如 entity_id、name、category、modality、source_path、text。

    舊版本機 FAISS 設定保留備查，不再於正式流程使用：
    # GUIDE_VECTOR_DB_DIR=data/vector_db/gemini_embedding_2
    # GUIDE_VECTOR_INDEX_FILE=resort_knowledge.faiss
    # GUIDE_VECTOR_METADATA_FILE=resort_knowledge.pkl
    """

    def __init__(self):
        self.collection_name = settings.GUIDE_QDRANT_COLLECTION_NAME
        self.client = QdrantClient(
            url=settings.GUIDE_QDRANT_URL,
            api_key=settings.GUIDE_QDRANT_API_KEY,
            timeout=int(getattr(settings, "GUIDE_QDRANT_TIMEOUT_SECONDS", 180)),
        )
        self._validate_collection_dimension()

    def _validate_collection_dimension(self) -> None:
        """啟動時先確認 Qdrant collection 維度與 Guide embedding 維度一致。"""
        try:
            info = self.client.get_collection(collection_name=self.collection_name)
            actual_dim = info.config.params.vectors.size
            expected_dim = int(settings.GUIDE_EMBEDDING_DIM)
        except Exception as e:
            raise RuntimeError(
                f"Guide Qdrant collection 讀取失敗：{self.collection_name}，原因：{e}"
            ) from e

        if actual_dim != expected_dim:
            raise RuntimeError(
                "Guide Qdrant collection 維度不一致："
                f"collection={self.collection_name}, "
                f"actual_dim={actual_dim}, expected_dim={expected_dim}。"
                "請確認 GUIDE_EMBEDDING_DIM，或重新 build Guide Qdrant collection。"
            )

    @staticmethod
    def _build_filter(filters: dict[str, Any] | None) -> Filter | None:
        """把原本 Python dict filters 轉成 Qdrant Filter。"""
        if not filters:
            return None

        conditions = []
        for key, expected_value in filters.items():
            if expected_value is None:
                continue

            if isinstance(expected_value, (list, tuple, set)):
                conditions.append(
                    FieldCondition(
                        key=key,
                        match=MatchAny(any=list(expected_value)),
                    )
                )
            else:
                conditions.append(
                    FieldCondition(
                        key=key,
                        match=MatchValue(value=expected_value),
                    )
                )

        if not conditions:
            return None

        return Filter(must=conditions)

    @staticmethod
    def _point_to_record(point: Any) -> dict[str, Any]:
        """把 Qdrant ScoredPoint / Record 轉回原本 guide_service 使用的 record dict。"""
        record = dict(getattr(point, "payload", None) or {})

        score = getattr(point, "score", None)
        if score is not None:
            record["score"] = float(score)

        point_id = getattr(point, "id", None)
        if point_id is not None:
            record["point_id"] = str(point_id)

        return record

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
        fetch_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        使用 Qdrant 線上向量搜尋。

        參數名稱保留原本 FAISS 版介面，讓 guide_service.py 不需要大幅改動。
        fetch_k 在 Qdrant 模式下用來當作 limit 的上限候選；若沒有特殊 filter，通常 top_k 即可。
        """
        top_k = int(top_k or settings.GUIDE_TOP_K)
        limit = int(fetch_k or top_k)
        limit = max(limit, top_k)

        query_filter = self._build_filter(filters)

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=vector_to_list(query_vector),
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        results = [self._point_to_record(point) for point in response.points]
        return results[:top_k]

    def scroll_records(
        self,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
        batch_size: int = 256,
    ) -> list[dict[str, Any]]:
        """使用 Qdrant scroll 取得符合 payload filter 的 records。"""
        query_filter = self._build_filter(filters)
        records: list[dict[str, Any]] = []
        next_offset = None

        while True:
            current_limit = batch_size
            if limit is not None:
                remaining = limit - len(records)
                if remaining <= 0:
                    break
                current_limit = min(batch_size, remaining)

            points, next_offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=query_filter,
                limit=current_limit,
                offset=next_offset,
                with_payload=True,
                with_vectors=False,
            )

            records.extend(self._point_to_record(point) for point in points)

            if next_offset is None:
                break

        return records

    def get_entity_records(
        self,
        entity_id: str,
        modality: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {"entity_id": entity_id}
        if modality:
            filters["modality"] = modality

        return self.scroll_records(filters=filters, limit=limit)

    def find_entity_by_title(self, title: str) -> dict[str, Any] | None:
        """
        結果頁追問時，前端只會帶 attraction_title。
        這裡從 Qdrant payload 反查對應 entity_id。
        """
        title = (title or "").strip()
        if not title:
            return None

        # 先做精準比對，避免同名片段誤判。
        for field in ["name", "title"]:
            records = self.scroll_records(filters={field: title}, limit=1)
            if records:
                return records[0]

        # 再做寬鬆比對。資料量目前約千筆，scroll 全部仍可接受。
        for record in self.scroll_records(limit=None):
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

        # HEIC / HEIF 不降權，因為 GuideImageService 會即時轉成 JPG 回傳。
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
        """將多筆相似結果依 entity_id 聚合，找出最可能的地點。"""
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
