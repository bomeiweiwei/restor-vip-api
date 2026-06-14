class RagTool:

    def search(
        self,
        query: str,
        qa_category: str,
    ) -> str:

        return (
            "[RAG Tool]\n"
            f"分類：{qa_category}\n"
            f"查詢：{query}\n"
            "目前尚未串接 Qdrant。"
        )


rag_tool = RagTool()