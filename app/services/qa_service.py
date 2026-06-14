from app.schemas.assistant import AssistantResponse, IntentResult
from app.agents.resort_qa_agent_service import resort_qa_agent_service
from app.agents.weather_agent_service import weather_agent_service
from app.agents.traffic_agent_service import traffic_agent_service


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

        return AssistantResponse(
            reply=(
                "[QA 問答流程]\n"
                f"原始問題：{message}\n"
                f"信心分數：{intent_result.confidence}\n"
                f"原因：{intent_result.reason}\n\n"
                + "\n\n".join(task_results)
            )
        )


qa_service = QAService()