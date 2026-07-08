from abc import ABC, abstractmethod
from langchain_core.messages import HumanMessage, SystemMessage


class BaseAILangchain(ABC):
    def __init__(self):
        self.llm = None

    def invoke(self, prompt) -> str:
        response = self.llm.invoke(prompt)

        if hasattr(response, "content"):
            return self._content_to_text(response.content)

        return str(response)

    @staticmethod
    def _content_to_text(content) -> str:
        """Normalize LangChain message content into plain text.

        Newer models (e.g. Gemini 3+) return `content` as a list of content
        blocks (`{"type": "text", "text": "...", ...}`) instead of a plain
        string.
        """
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            return "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )

        return str(content)

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