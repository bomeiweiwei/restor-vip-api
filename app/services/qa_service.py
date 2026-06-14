from app.schemas.assistant import AssistantResponse, IntentResult
from app.agents.resort_qa_agent_service import resort_qa_agent_service
from app.agents.weather_agent_service import weather_agent_service
from app.agents.traffic_agent_service import traffic_agent_service

from langchain_core.prompts import ChatPromptTemplate

from app.ai.factory import create_ai_langchain
from app.core.config import settings
from app.prompts.qa_answer_prompt import QA_ANSWER_SYSTEM_PROMPT


RAG_CATEGORIES = {
    "facility_hours",
    "attraction_hours",
    "facility_info",
    "rules",
    "price",
    "restaurant",
    "attraction",
    "room_facility",
    "room_service",
}


class QAService:
    def __init__(self):
        self.llm = create_ai_langchain(settings.AI_PROVIDER).llm

        self.answer_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", QA_ANSWER_SYSTEM_PROMPT),
                (
                    "human",
                    """
    旅客原始問題：
    {message}

    查詢結果：
    {tool_results}

    請產生給旅客看的最終回答。
    """,
                ),
            ]
        )

        self.answer_chain = self.answer_prompt | self.llm

    def process(
        self,
        message: str,
        intent_result: IntentResult,
    ) -> AssistantResponse:

        task_results: list[str] = []

        for task in intent_result.qa_tasks:
            category = task.qa_category
            query = task.query

            if category == "weather":
                result = weather_agent_service.answer(query)

            elif category == "traffic":
                result = traffic_agent_service.answer(query)

            elif category in RAG_CATEGORIES:
                result = resort_qa_agent_service.answer(
                    query=query,
                    qa_category=category,
                )

            else:
                result = (
                    f"無法處理的 QA 類別：{category}"
                )

            task_results.append(
                (
                    f"分類：{category}\n"
                    f"查詢：{query}\n"
                    f"{result}"
                )
            )

        final_answer = self.answer_chain.invoke(
            {
                "message": message,
                "tool_results": "\n\n".join(task_results),
            }
        )

        reply = (
            final_answer.content
            if hasattr(final_answer, "content")
            else str(final_answer)
        )

        return AssistantResponse(reply=reply)


qa_service = QAService()