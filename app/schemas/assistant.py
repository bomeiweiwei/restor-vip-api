from pydantic import BaseModel, Field
from typing import Literal


class SpeechToTextResponse(BaseModel):
    text: str


class AssistantRequest(BaseModel):
    message: str


class AssistantResponse(BaseModel):
    text: str | None = None
    reply: str
    language: Literal["zh-TW", "en-US", "ja-JP", "ko-KR"] | None = "zh-TW"

class QATask(BaseModel):
    qa_category: Literal[
        "facility_hours",
        "attraction_hours",
        "facility_info",
        "rules",
        "price",
        "weather",
        "traffic",
        "restaurant",
        "attraction",
        "room_facility",
        "room_service",
    ]

    query: str = Field(
        description="針對此分類整理後的查詢文字"
    )


class IntentResult(BaseModel):
    intent: Literal["qa", "service_request"]

    qa_tasks: list[QATask] = Field(
        default_factory=list,
        description="QA 任務清單；service_request 時必須是空陣列"
    )

    confidence: float
    reason: str

class TextToSpeechRequest(BaseModel):
    text: str = Field(..., min_length=1)
    language: str = "zh-TW"