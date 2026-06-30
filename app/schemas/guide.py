from typing import Optional

from pydantic import BaseModel


class GuideAnalyzeResponse(BaseModel):
    success: bool
    title: str
    location: str
    guideMessage: str
    audioUrl: Optional[str] = ""
    imageUrl: Optional[str] = ""
    user_text: Optional[str] = ""
    responseLanguage: Optional[str] = "zh-TW"
    audio_base64: str | None = None


class GuideTextToSpeechRequest(BaseModel):
    text: str
    language: str = "zh-TW"
