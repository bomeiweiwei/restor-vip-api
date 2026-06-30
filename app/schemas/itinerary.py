from pydantic import BaseModel
from datetime import date, time


class ItineraryScheduleResponse(BaseModel):
    time: str
    title: str
    content: str
    preference: str | None = None
    imageUrl: str | None = None


class ItineraryDateGroupResponse(BaseModel):
    date: str
    schedules: list[ItineraryScheduleResponse]
    

class ItineraryFeedbackRequest(BaseModel):
    message: str
    date: str
    lang: str = "zh"  # 預設為中文，可傳入 "en"


class ItineraryFeedbackResponse(BaseModel):
    success: bool
    message: str
    audio_base64: str | None = None  # 🚀 新增：用來存放 MP3 的 Base64 字串