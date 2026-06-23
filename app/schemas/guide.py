from pydantic import BaseModel


class GuideAnalyzeResponse(BaseModel):
    success: bool
    title: str
    location: str
    guideMessage: str
    audioUrl: str = ""
    imageUrl: str = ""
    user_text: str = ""
