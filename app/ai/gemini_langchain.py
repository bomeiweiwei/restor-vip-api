from app.ai.base import BaseAILangchain


class GeminiLangchain(BaseAILangchain):
    def __init__(self, api_key: str, model_name: str):
        from langchain_google_genai import ChatGoogleGenerativeAI

        self.llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
        )