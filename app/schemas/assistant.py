from pydantic import BaseModel


class SpeechToTextResponse(BaseModel):
    text: str


class AssistantRequest(BaseModel):
    message: str


class AssistantResponse(BaseModel):
    reply: str