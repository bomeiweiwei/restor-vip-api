from app.schemas.assistant import AssistantResponse, IntentResult
from app.services.rag_search_service import rag_search_service
from app.services.weather_service import weather_service
from app.services.traffic_service import traffic_service


class QAService:

    def process(
        self,
        message: str,
        intent_result: IntentResult,
    ) -> AssistantResponse:

        tool_results: list[str] = []

        for task in intent_result.qa_tasks:
            category = task.qa_category
            query = task.query

            if category == "weather":
                tool_result = weather_service.search(query)

            elif category == "traffic":
                tool_result = traffic_service.search(query)

            else:
                tool_result = rag_search_service.search(
                    message=query,
                    qa_category=category,
                )

            tool_results.append(
                (
                    f"分類：{category}\n"
                    f"查詢：{query}\n"
                    f"工具結果：{tool_result}"
                )
            )

        return AssistantResponse(
            reply=(
                "[QA 問答流程]\n"
                f"原始問題：{message}\n"
                f"信心分數：{intent_result.confidence}\n"
                f"原因：{intent_result.reason}\n\n"
                + "\n\n".join(tool_results)
            )
        )


qa_service = QAService()