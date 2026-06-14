from abc import ABC, abstractmethod
from langchain_core.messages import HumanMessage, SystemMessage


class BaseAILangchain(ABC):
    def __init__(self):
        self.llm = None

    def invoke(self, prompt) -> str:
        response = self.llm.invoke(prompt)

        if hasattr(response, "content"):
            return response.content

        return str(response)

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        return self.invoke(messages)

    def chat_with_images(self, system_prompt: str, human_messages: list) -> str:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_messages),
        ]

        return self.invoke(messages)