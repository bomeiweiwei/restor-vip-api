import json
import wave
from functools import lru_cache
from io import BytesIO

from google import genai
from google.genai import types
from google.oauth2 import service_account

from app.core.config import settings


class GeminiTtsService:
    def __init__(self):
        self.client = self._create_client()

    def _create_client(self) -> genai.Client:
        credentials = None

        if settings.GOOGLE_CREDENTIALS_JSON:
            try:
                credentials_info = json.loads(settings.GOOGLE_CREDENTIALS_JSON)
                credentials = service_account.Credentials.from_service_account_info(
                    credentials_info,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
                print("✅ 成功從 Pydantic Settings 載入 GCP 憑證字串。")
            except Exception as e:
                print(f"❌ 解析 GOOGLE_CREDENTIALS_JSON 失敗: {e}")
                raise RuntimeError("GOOGLE_CREDENTIALS_JSON 解析失敗") from e

        if not settings.GOOGLE_CLOUD_PROJECT:
            raise RuntimeError("缺少 GOOGLE_CLOUD_PROJECT")

        return genai.Client(
            vertexai=True,
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
            credentials=credentials,
        )

    def synthesize(self, text: str, language: str = "zh-TW") -> bytes:
        if not text or not text.strip():
            raise ValueError("TTS text 不可為空")

        prompt = self._build_prompt(text=text.strip(), language=language)

        response = self.client.models.generate_content(
            model=settings.GEMINI_TTS_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=settings.GEMINI_TTS_VOICE,
                        )
                    )
                ),
            ),
        )

        audio_data = self._extract_audio_bytes(response)

        # Gemini TTS 常見回傳是 PCM audio，需要包成 WAV，瀏覽器才好播放
        return self._pcm_to_wav(audio_data)

    def _extract_audio_bytes(self, response) -> bytes:
        try:
            parts = response.candidates[0].content.parts

            for part in parts:
                inline_data = getattr(part, "inline_data", None)
                if inline_data and inline_data.data:
                    return inline_data.data

        except Exception as e:
            raise RuntimeError(f"解析 Gemini TTS 音訊失敗: {e}") from e

        raise RuntimeError("Gemini TTS 沒有回傳音訊資料")

    def _pcm_to_wav(self, pcm_data: bytes) -> bytes:
        buffer = BytesIO()

        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)
            wav_file.writeframes(pcm_data)

        return buffer.getvalue()

    def _build_prompt(self, text: str, language: str) -> str:
        if language == "en-US":
            return (
                "Read the following text as an enthusiastic and professional customer service representative "
                "with a lively, upbeat tone. Speak naturally and warmly, as if you're genuinely excited to help:\n"
                f"{text}"
            )

        if language == "ja-JP":
            return (
                "次の文章を、明るく活発でプロフェッショナルなカスタマーサービス担当者として、"
                "自然でエネルギッシュな話し方で読み上げてください：\n"
                f"{text}"
            )

        if language == "ko-KR":
            return (
                "다음 문장을 밝고 활기차며 전문적인 고객 서비스 담당자처럼 "
                "자연스럽고 생동감 있는 말투로 읽어주세요:\n"
                f"{text}"
            )

        return (
            "請用活潑、熱情、專業的客服人員語氣，自然地朗讀以下文字，"
            "語調輕快有朝氣，讓人感受到你真心想要協助的誠意：\n"
            f"{text}"
        )


@lru_cache
def get_gemini_tts_service() -> GeminiTtsService:
    return GeminiTtsService()