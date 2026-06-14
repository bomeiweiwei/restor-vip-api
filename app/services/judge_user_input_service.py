from app.schemas.assistant import AssistantResponse
from app.services.intent_classifier_service import intent_classifier_service


class JudgeUserInputService:

    def judge(
        self,
        message: str,
    ) -> AssistantResponse:

        intent_result = intent_classifier_service.classify(message)

        if intent_result.intent == "qa":
            return AssistantResponse(
                reply=(
                    "已判斷為 QA 問答\n"
                    f"分類：{intent_result.qa_category}\n"
                    f"信心分數：{intent_result.confidence}\n"
                    f"原因：{intent_result.reason}"
                )
            )

        return AssistantResponse(
            reply=(
                "已判斷為客服需求\n"
                f"信心分數：{intent_result.confidence}\n"
                f"原因：{intent_result.reason}"
            )
        )


judge_user_input_service = JudgeUserInputService()