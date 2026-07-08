import json

from app.ai.base import BaseAILangchain


class GeminiLangchain(BaseAILangchain):
    def __init__(self, credentials_json: str, project_id: str, model_name: str):
        from google.oauth2 import service_account
        from langchain_google_genai import ChatGoogleGenerativeAI

        credentials_info = json.loads(credentials_json)

        credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )

        self.llm = ChatGoogleGenerativeAI(
            model=model_name,
            credentials=credentials,
            vertexai=True,
            project=project_id,
            location="global"
        )