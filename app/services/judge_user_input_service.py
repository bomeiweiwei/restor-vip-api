from app.services.intent_classifier_service import (
    intent_classifier_service,
)

from app.services.qa_service import (
    qa_service,
)

from app.services.customer_service_request_service import (
    customer_service_request_service,
)

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

        return customer_service_request_service.process(
            db=db, current_user=current_user, message=message
        )


judge_user_input_service = JudgeUserInputService()
