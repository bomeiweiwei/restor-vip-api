from pydantic import BaseModel
from typing import Literal


class SpeechToTextResponse(BaseModel):
    text: str


class AssistantRequest(BaseModel):
    message: str


class AssistantResponse(BaseModel):
    reply: str
    language: Literal["zh-TW", "en-US", "ja-JP", "ko-KR"] | None = "zh-TW"