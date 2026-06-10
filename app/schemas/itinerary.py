from pydantic import BaseModel
from datetime import date, time


class ItineraryScheduleResponse(BaseModel):
    time: str
    title: str
    content: str
    preference: str | None = None


class ItineraryDateGroupResponse(BaseModel):
    date: str
    schedules: list[ItineraryScheduleResponse]
    

class ItineraryFeedbackRequest(BaseModel):
    message: str


class ItineraryFeedbackResponse(BaseModel):
    success: bool
    message: str