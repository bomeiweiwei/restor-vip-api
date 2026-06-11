import os
import tempfile
import subprocess

import azure.cognitiveservices.speech as speechsdk
from fastapi import UploadFile

from app.core.config import settings


class SpeechToTextService:

    async def transcribe_upload_file(
        self,
        file: UploadFile,
    ) -> str:
        webm_path = None
        wav_path = None

        try:
            azure_speech_key = settings.AZURE_SPEECH_KEY
            azure_speech_region = settings.AZURE_SPEECH_REGION

            if not azure_speech_key or not azure_speech_region:
                return "Azure Speech 設定不存在，請確認 AZURE_SPEECH_KEY 與 AZURE_SPEECH_REGION"

            with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_webm:
                content = await file.read()
                temp_webm.write(content)
                webm_path = temp_webm.name

            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_wav:
                wav_path = temp_wav.name

            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    webm_path,
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    wav_path,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )

            speech_config = speechsdk.SpeechConfig(
                subscription=azure_speech_key,
                region=azure_speech_region,
            )

            auto_detect_config = (
                speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
                    languages=["en-US", "zh-TW", "ko-KR", "ja-JP"]
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
                return result.text

            if result.reason == speechsdk.ResultReason.NoMatch:
                return "無法辨識語音內容"

            if result.reason == speechsdk.ResultReason.Canceled:
                cancellation = result.cancellation_details
                return f"辨識失敗：{cancellation.reason}"

            return "未知錯誤"

        except subprocess.CalledProcessError:
            return "ffmpeg 轉檔失敗"

        except Exception as e:
            return f"系統錯誤：{str(e)}"

        finally:
            for path in [webm_path, wav_path]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except PermissionError:
                        pass


speech_to_text_service = SpeechToTextService()
