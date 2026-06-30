import os
import tempfile
import threading

import azure.cognitiveservices.speech as speechsdk
from azure.cognitiveservices.speech import PropertyId
from fastapi import UploadFile

from app.core.config import settings


class AzureSpeechToTextService:

    async def transcribe_upload_file(
        self,
        file: UploadFile,
    ) -> dict:
        wav_path = None

        try:
            azure_speech_key = settings.AZURE_SPEECH_KEY
            azure_speech_region = settings.AZURE_SPEECH_REGION

            if not azure_speech_key or not azure_speech_region:
                return {
                    "text": "Azure Speech 設定不存在，請確認 AZURE_SPEECH_KEY 與 AZURE_SPEECH_REGION",
                    "language": "zh-TW",
                }

            content = await file.read()

            if not content:
                return {
                    "text": "沒有收到音訊檔案",
                    "language": "zh-TW",
                }

            print("收到音訊大小:", len(content), "bytes")
            print("content_type:", file.content_type)

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

            texts: list[str] = []
            detected_language = "zh-TW"
            done = threading.Event()
            error_message = None

            def recognized_handler(evt):
                nonlocal detected_language

                if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                    text = evt.result.text

                    if text:
                        print("辨識片段:", text)
                        texts.append(text)

                    lang = evt.result.properties.get(
                        PropertyId.SpeechServiceConnection_AutoDetectSourceLanguageResult
                    )

                    if lang:
                        detected_language = lang

            def canceled_handler(evt):
                nonlocal error_message

                cancellation = evt.result.cancellation_details

                if cancellation.reason == speechsdk.CancellationReason.EndOfStream:
                    done.set()
                    return

                error_message = f"辨識取消：{cancellation.reason}"
                if cancellation.error_details:
                    error_message += f"，詳細：{cancellation.error_details}"

                print(error_message)
                done.set()

            def session_stopped_handler(evt):
                print("語音辨識 session 結束")
                done.set()

            recognizer.recognized.connect(recognized_handler)
            recognizer.canceled.connect(canceled_handler)
            recognizer.session_stopped.connect(session_stopped_handler)

            recognizer.start_continuous_recognition()
            done.wait()
            recognizer.stop_continuous_recognition()

            if error_message and not texts:
                return {
                    "text": error_message,
                    "language": detected_language,
                }

            final_text = " ".join(texts).strip()

            if not final_text:
                return {
                    "text": "無法辨識語音內容",
                    "language": detected_language,
                }

            print("完整辨識結果:", final_text)
            print("偵測語言:", detected_language)

            return {
                "text": final_text,
                "language": detected_language,
            }

        except Exception as e:
            return {
                "text": f"系統錯誤：{str(e)}",
                "language": "zh-TW",
            }

        finally:
            if wav_path and os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except PermissionError:
                    pass


azure_speech_to_text_service = AzureSpeechToTextService()