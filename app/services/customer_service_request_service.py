from app.schemas.assistant import AssistantResponse


class CustomerServiceRequestService:

    def process(
        self,
        message: str,
    ) -> AssistantResponse:

        return AssistantResponse(
            reply=(
                "[客服需求流程]\n"
                f"已收到您的需求：{message}"
            )
        )


customer_service_request_service = (
    CustomerServiceRequestService()
)