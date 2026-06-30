import json
import wave
from functools import lru_cache
from io import BytesIO

from google import genai
from google.genai import types
from google.cloud import texttospeech
from google.oauth2 import service_account

import base64

from app.core.config import settings


class GeminiTtsService:
    _VOICE_BY_LANGUAGE = {
        "en-US": ("en-US", "en-US-Wavenet-F"),
        "ja-JP": ("ja-JP", "ja-JP-Wavenet-B"),
        "ko-KR": ("ko-KR", "ko-KR-Wavenet-A"),
    }
    _DEFAULT_VOICE = ("cmn-TW", "cmn-TW-Wavenet-A")

    def __init__(self):
        credentials = self._load_credentials()
        self.client = self._create_client(credentials)
        self.tts_client = self._create_tts_client(credentials)

    def _load_credentials(self) -> service_account.Credentials | None:
        if not settings.GOOGLE_CREDENTIALS_JSON:
            return None

        try:
            credentials_info = json.loads(settings.GOOGLE_CREDENTIALS_JSON)
            credentials = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            print("✅ 成功從 Pydantic Settings 載入 GCP 憑證字串。")
            return credentials
        except Exception as e:
            print(f"❌ 解析 GOOGLE_CREDENTIALS_JSON 失敗: {e}")
            raise RuntimeError("GOOGLE_CREDENTIALS_JSON 解析失敗") from e

    def _create_client(self, credentials) -> genai.Client:
        if not settings.GOOGLE_CLOUD_PROJECT:
            raise RuntimeError("缺少 GOOGLE_CLOUD_PROJECT")

        return genai.Client(
            vertexai=True,
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
            credentials=credentials,
        )

    def _create_tts_client(self, credentials) -> texttospeech.TextToSpeechClient:
        if credentials:
            return texttospeech.TextToSpeechClient(credentials=credentials)
        return texttospeech.TextToSpeechClient()

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
    
    def synthesize_base64(
        self,
        text: str,
        language: str,
    ) -> str:
        if not text or not text.strip():
            raise ValueError("TTS text 不可為空")

        synthesis_input = texttospeech.SynthesisInput(text=text.strip())
        voice = self._build_voice_params(language)
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.15,
            pitch=1.0,
        )

        response = self.tts_client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )

        return base64.b64encode(response.audio_content).decode("utf-8")

    def _build_voice_params(self, language: str) -> texttospeech.VoiceSelectionParams:
        language_code, voice_name = self._VOICE_BY_LANGUAGE.get(
            language, self._DEFAULT_VOICE
        )
        return texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name,
        )


@lru_cache
def get_gemini_tts_service() -> GeminiTtsService:
    return GeminiTtsService()