from app.tools.rag_tool import rag_tool


class ResortQAAgentService:

    def answer(
        self,
        query: str,
        qa_category: str,
    ) -> str:

        return rag_tool.search(
            query=query,
            qa_category=qa_category,
        )


resort_qa_agent_service = ResortQAAgentService()