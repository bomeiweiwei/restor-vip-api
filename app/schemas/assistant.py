from pydantic import BaseModel, Field
from typing import Literal


class SpeechToTextResponse(BaseModel):
    text: str


class AssistantRequest(BaseModel):
    message: str


class AssistantResponse(BaseModel):
    reply: str
    language: Literal["zh-TW", "en-US", "ja-JP", "ko-KR"] | None = "zh-TW"

class IntentResult(BaseModel):
    intent: Literal["qa", "service_request"] = Field(
        description="使用者意圖，只能是 qa 或 service_request"
    )
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
    ] | None = Field(
        default=None,
        description="QA 問題類別；如果 intent 是 service_request，必須是 null",
    )
    confidence: float = Field(
        description="分類信心分數，0 到 1"
    )
    reason: str = Field(
        description="一句繁體中文判斷原因"
    )