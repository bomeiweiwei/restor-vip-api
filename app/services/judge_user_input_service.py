from app.services.intent_classifier_service import (
    intent_classifier_service,
)

from app.services.qa_service import (
    qa_service,
)

from app.services.customer_service_request_service import (
    customer_service_request_service,
)

from app.schemas.assistant import AssistantResponse

from sqlalchemy.orm import Session


class JudgeUserInputService:

    def judge(
        self,
        db: Session,
        current_user: dict,
        message: str,
    ):

        result = intent_classifier_service.classify(message)

        if result.intent == "qa":
            return qa_service.process(
                message=message,
                intent_result=result,
            )
        if result.intent == "service_request":
            return customer_service_request_service.process(
                db=db, current_user=current_user, message=result.service_request_message or message,
            )
        return AssistantResponse(
            reply=(
                "抱歉，我目前只能協助渡假村相關問題或客服需求。"
            )
        )


judge_user_input_service = JudgeUserInputService()
