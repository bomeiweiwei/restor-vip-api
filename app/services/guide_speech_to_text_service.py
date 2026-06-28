import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import azure.cognitiveservices.speech as speechsdk
from azure.cognitiveservices.speech import PropertyId
from fastapi import UploadFile

from app.core.config import settings


class GuideSpeechToTextService:
    """
    專屬導遊專用 STT。

    設計原因：
    - 瀏覽器 MediaRecorder 常見輸出是 webm/ogg/mp4，不一定是真正 wav。
    - 專屬導遊先用 ffmpeg 統一轉成 16kHz mono wav，再交給 Azure Speech。
    - 不修改正式後端既有 speech_to_text_service.py，避免影響其他功能。
    """

    def _find_ffmpeg(self) -> str:
        env_path = str(getattr(settings, "FFMPEG_PATH", "") or "").strip().strip('"').strip("'")

        if env_path and Path(env_path).exists():
            return env_path

        system_path = shutil.which("ffmpeg")
        if system_path:
            return system_path

        raise RuntimeError(
            "找不到 ffmpeg。請先安裝 ffmpeg，或在 .env 設定 FFMPEG_PATH，例如：FFMPEG_PATH=C:/ffmpeg/bin/ffmpeg.exe"
        )

    @staticmethod
    def _guess_suffix(upload_file: UploadFile) -> str:
        filename_suffix = Path(upload_file.filename or "").suffix.lower()
        if filename_suffix:
            return filename_suffix

        content_type = (upload_file.content_type or "").lower()
        if "webm" in content_type:
            return ".webm"
        if "ogg" in content_type:
            return ".ogg"
        if "mp4" in content_type or "m4a" in content_type:
            return ".m4a"
        if "mpeg" in content_type or "mp3" in content_type:
            return ".mp3"
        if "wav" in content_type or "wave" in content_type:
            return ".wav"
        return ".webm"

    async def _save_upload_file(self, upload_file: UploadFile) -> Path:
        suffix = self._guess_suffix(upload_file)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_path = Path(temp_file.name)

        try:
            content = await upload_file.read()
            print(f"[GUIDE STT] upload filename={upload_file.filename}")
            print(f"[GUIDE STT] upload content_type={upload_file.content_type}")
            print(f"[GUIDE STT] upload size={len(content)} bytes")

            if not content:
                raise RuntimeError("沒有收到音訊檔案。")

            temp_file.write(content)
            temp_file.close()
            return temp_path

        except Exception:
            temp_file.close()
            temp_path.unlink(missing_ok=True)
            raise

    def _convert_to_wav(self, input_path: Path) -> Path:
        ffmpeg = self._find_ffmpeg()
        output_path = input_path.with_suffix(".converted.wav")

        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "wav",
            str(output_path),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )

        if result.returncode != 0:
            raise RuntimeError(
                "ffmpeg 音訊轉檔失敗。\n"
                f"cmd={' '.join(cmd)}\n"
                f"stderr={result.stderr}"
            )

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("ffmpeg 轉檔後沒有產生有效 WAV。")

        print(f"[GUIDE STT] converted wav={output_path}")
        print(f"[GUIDE STT] converted size={output_path.stat().st_size} bytes")
        return output_path

    def _recognize_wav(self, wav_path: Path) -> dict:
        speech_key = str(settings.AZURE_SPEECH_KEY or "").strip().strip('"').strip("'")
        speech_region = str(settings.AZURE_SPEECH_REGION or "").strip().strip('"').strip("'")

        if not speech_key or not speech_region:
            raise RuntimeError("AZURE_SPEECH_KEY 或 AZURE_SPEECH_REGION 尚未設定。")

        print("[GUIDE STT] speech_key exists =", bool(speech_key))
        print("[GUIDE STT] speech_region =", repr(speech_region))

        speech_config = speechsdk.SpeechConfig(
            subscription=speech_key,
            region=speech_region,
        )

        auto_detect_config = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
            languages=["zh-TW", "en-US", "ja-JP", "ko-KR"]
        )

        audio_config = speechsdk.audio.AudioConfig(filename=str(wav_path))

        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
            auto_detect_source_language_config=auto_detect_config,
        )

        result = recognizer.recognize_once()

        detected_language = "zh-TW"
        try:
            lang = result.properties.get(PropertyId.SpeechServiceConnection_AutoDetectSourceLanguageResult)
            if lang:
                detected_language = lang
        except Exception:
            pass

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            return {
                "text": (result.text or "").strip(),
                "language": detected_language,
            }

        if result.reason == speechsdk.ResultReason.NoMatch:
            return {
                "text": "",
                "language": detected_language,
                "error": "無法辨識語音內容。請靠近麥克風，並以較清楚的語速再試一次。",
            }

        if result.reason == speechsdk.ResultReason.Canceled:
            cancellation = speechsdk.CancellationDetails(result)
            detail = f"語音辨識取消：{cancellation.reason}"
            if cancellation.error_details:
                detail += f"，詳細：{cancellation.error_details}"
            return {
                "text": "",
                "language": detected_language,
                "error": detail,
            }

        return {
            "text": "",
            "language": detected_language,
            "error": f"未知語音辨識狀態：{result.reason}",
        }

    async def transcribe_upload_file(self, upload_file: UploadFile) -> dict:
        input_path: Path | None = None
        wav_path: Path | None = None

        try:
            input_path = await self._save_upload_file(upload_file)
            wav_path = self._convert_to_wav(input_path)
            return self._recognize_wav(wav_path)

        finally:
            if input_path:
                input_path.unlink(missing_ok=True)
            if wav_path:
                wav_path.unlink(missing_ok=True)


guide_speech_to_text_service = GuideSpeechToTextService()
