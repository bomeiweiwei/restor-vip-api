from pydantic import BaseModel
from datetime import date, time
from typing import Optional  # 🚀 補上這行


class ItineraryScheduleResponse(BaseModel):
    time: str
    title: str
    content: str
    preference: str | None = None
    imageUrl: Optional[str] = None


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