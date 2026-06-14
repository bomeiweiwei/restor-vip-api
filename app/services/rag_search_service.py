import os
from functools import lru_cache
from typing import Any

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client.models import FieldCondition, Filter, MatchAny

from app.ai.embedding_factory import get_embedding_function
from app.core.config import settings


class RagSearchService:
    def __init__(self):
        self._validate_env()
        self.vector_db = self._load_vector_db()

    def _validate_env(self):
        if not settings.QDRANT_URL:
            raise ValueError("缺少 QDRANT_URL")

        if not settings.QDRANT_API_KEY:
            raise ValueError("缺少 QDRANT_API_KEY")

        if not settings.QDRANT_COLLECTION_NAME:
            raise ValueError("缺少 QDRANT_COLLECTION_NAME")

    def _load_vector_db(self) -> QdrantVectorStore:
        embedding_function = get_embedding_function()

        return QdrantVectorStore.from_existing_collection(
            embedding=embedding_function,
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            collection_name=settings.QDRANT_COLLECTION_NAME,
        )

    def _build_category_filter(
        self,
        categories: list[str] | None,
    ) -> Filter | None:
        if not categories:
            return None

        return Filter(
            must=[
                FieldCondition(
                    key="metadata.category",
                    match=MatchAny(any=categories),
                )
            ]
        )

    def _build_query_text(
        self,
        user_question: str,
        categories: list[str] | None,
    ) -> str:
        if categories:
            category_text = "、".join(categories)

            return f"""
使用者正在詢問渡假村相關資訊。
目前問題可能屬於以下資料分類：{category_text}

請搜尋與以下問題最相關的內容：
- 名稱
- 特色
- 說明
- 適合族群
- 營業時間
- 注意事項
- 價格
- 服務內容

使用者問題：
{user_question}
""".strip()

        return f"""
使用者正在詢問渡假村相關資訊。
請搜尋與以下問題最相關的內容：

使用者問題：
{user_question}
""".strip()

    def search_knowledge_by_categories(
        self,
        user_question: str,
        categories: list[str] | None = None,
        k: int = 1,
    ) -> list[dict[str, Any]]:
        query_text = self._build_query_text(
            user_question=user_question,
            categories=categories,
        )

        results = self.vector_db.similarity_search_with_score(
            query=query_text,
            k=k,
            filter=self._build_category_filter(categories),
        )

        return [
            self._format_result(doc, score)
            for doc, score in results
        ]

    def search_without_category(
        self,
        user_question: str,
        k: int = 5,
    ) -> list[dict[str, Any]]:
        return self.search_knowledge_by_categories(
            user_question=user_question,
            categories=None,
            k=k,
        )

    def _format_result(
        self,
        doc: Document,
        score: float,
    ) -> dict[str, Any]:
        metadata = doc.metadata or {}

        return {
            "content": doc.page_content,
            "score": float(score),
            "metadata": {
                # "location_scope": metadata.get("location_scope"),
                "category": metadata.get("category"),
                "place_name": metadata.get("place_name"),
                # "source_file": metadata.get("source_file"),
                # "source_path": metadata.get("source_path"),
                # "page": metadata.get("page"),
            },
        }


@lru_cache
def get_rag_search_service() -> RagSearchService:
    return RagSearchService()