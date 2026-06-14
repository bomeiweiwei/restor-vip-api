class RagSearchService:

    def search(
        self,
        message: str,
        qa_category: str | None,
    ) -> str:

        return (
            f"已進入 RAG 搜尋流程。"
            f"問題：{message}；"
            f"分類：{qa_category}。"
            f"目前尚未串接 Qdrant。"
        )


rag_search_service = RagSearchService()