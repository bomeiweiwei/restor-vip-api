import os
from openai import AzureOpenAI
from app.core.config import settings

class AzureOpenAITTSService:
    def __init__(self):
        self.client = AzureOpenAI(
            api_key=settings.AZURE_OPENAI_TTS_KEY,
            api_version=settings.AZURE_OPENAI_TTS_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_TTS_ENDPOINT,
        )

        self.deployment = settings.AZURE_OPENAI_TTS_DEPLOYMENT

        self.voice = settings.AZURE_OPENAI_TTS_VOICE

    def synthesize(self, text: str) -> bytes:
        if not text or not text.strip():
            raise ValueError("TTS text is empty")

        response = self.client.audio.speech.create(
            model=self.deployment,
            voice=self.voice,
            input=text.strip(),
            response_format="mp3",
            instructions=(
                "You are an enthusiastic and friendly hotel concierge who genuinely enjoys helping guests. "
                "Speak with energy and warmth — upbeat, cheerful, and engaging, like you are excited to share helpful information. "
                "Keep a natural, lively rhythm with expressive intonation; avoid sounding flat or robotic. "
                "Read numbers, dates, and place names smoothly without unnatural pauses."
            )
        )

        return response.read()


azure_openai_tts_service = AzureOpenAITTSService()