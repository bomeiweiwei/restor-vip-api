from app.schemas.assistant import (
    SpeechToTextResponse,
    AssistantResponse,
)


class AssistantService:

    def speech_to_text(
        self,
    ) -> SpeechToTextResponse:

        return SpeechToTextResponse(
            text="請推薦今晚餐廳"
        )

    def send_message(
        self,
        message: str,
    ) -> AssistantResponse:

        return AssistantResponse(
            reply=f"已收到您的訊息：{message}"
        )


assistant_service = AssistantService()