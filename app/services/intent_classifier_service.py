from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from app.ai.factory import create_ai_langchain
from app.core.config import settings
from app.prompts.intent_prompt import INTENT_SYSTEM_PROMPT
from app.schemas.assistant import IntentResult


class IntentClassifierService:
    def __init__(self):
        self.llm = create_ai_langchain(settings.AI_PROVIDER).llm

        self.parser = PydanticOutputParser(
            pydantic_object=IntentResult
        )

        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    INTENT_SYSTEM_PROMPT
                    + "\n\n請務必遵守以下輸出格式：\n{format_instructions}",
                ),
                (
                    "human",
                    "旅客輸入：{message}",
                ),
            ]
        )

        self.chain = (
            self.prompt
            | self.llm
            | self.parser
            | RunnableLambda(self._normalize_result)
        )

    def classify(self, message: str) -> IntentResult:
        return self.chain.invoke(
            {
                "message": message,
                "format_instructions": self.parser.get_format_instructions(),
            }
        )

    def _normalize_result(self, result: IntentResult) -> IntentResult:
        if result.intent == "service_request":
            result.qa_category = None

        if result.confidence < 0:
            result.confidence = 0

        if result.confidence > 1:
            result.confidence = 1

        return result


intent_classifier_service = IntentClassifierService()