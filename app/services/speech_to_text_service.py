import os
import tempfile

import azure.cognitiveservices.speech as speechsdk
from fastapi import UploadFile

from app.core.config import settings


class SpeechToTextService:

    async def transcribe_upload_file(
        self,
        file: UploadFile,
    ) -> str:
        wav_path = None

        try:
            azure_speech_key = settings.AZURE_SPEECH_KEY
            azure_speech_region = settings.AZURE_SPEECH_REGION

            if not azure_speech_key or not azure_speech_region:
                return "Azure Speech 設定不存在，請確認 AZURE_SPEECH_KEY 與 AZURE_SPEECH_REGION"

            content = await file.read()

            if not content:
                return "沒有收到音訊檔案"

            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_wav:
                temp_wav.write(content)
                wav_path = temp_wav.name

            speech_config = speechsdk.SpeechConfig(
                subscription=azure_speech_key,
                region=azure_speech_region,
            )

            auto_detect_config = (
                speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
                    languages=["zh-TW", "en-US", "ja-JP", "ko-KR"]
                )
            )

            audio_config = speechsdk.audio.AudioConfig(filename=wav_path)

            recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config,
                audio_config=audio_config,
                auto_detect_source_language_config=auto_detect_config,
            )

            result = recognizer.recognize_once()

            if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                # print(result.text)
                return result.text

            if result.reason == speechsdk.ResultReason.NoMatch:
                return "無法辨識語音內容"

            if result.reason == speechsdk.ResultReason.Canceled:
                cancellation = result.cancellation_details
                return f"辨識失敗：{cancellation.reason}"

            return "未知錯誤"

        except Exception as e:
            return f"系統錯誤：{str(e)}"

        finally:
            if wav_path and os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except PermissionError:
                    pass


speech_to_text_service = SpeechToTextService()