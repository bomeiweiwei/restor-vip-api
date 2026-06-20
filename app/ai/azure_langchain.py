from app.ai.base import BaseAILangchain


class AzureLangchain(BaseAILangchain):
    def __init__(self, api_key: str, endpoint: str, deployment_name: str):
        from langchain_openai import ChatOpenAI

        self.llm = ChatOpenAI(
            model=deployment_name,
            base_url=endpoint,
            api_key=api_key,
        )