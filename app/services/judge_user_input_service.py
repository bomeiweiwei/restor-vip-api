from app.schemas.assistant import AssistantResponse


class JudgeUserInputService:

    def judge(
        self,
        message: str,
    ) -> AssistantResponse:

        return AssistantResponse(reply=f"{message}")


judge_user_input_service = JudgeUserInputService()