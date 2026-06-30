import json

from fastapi import UploadFile
from google import genai
from google.genai import types
from google.oauth2 import service_account

from app.core.config import settings


class GeminiSpeechToTextService:
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
                print("成功從 Pydantic Settings 載入 GCP 憑證字串。")
            except Exception as e:
                print(f"解析 GOOGLE_CREDENTIALS_JSON 失敗: {e}")
                raise RuntimeError("GOOGLE_CREDENTIALS_JSON 解析失敗") from e

        if not settings.GOOGLE_CLOUD_PROJECT:
            raise RuntimeError("缺少 GOOGLE_CLOUD_PROJECT")

        if not settings.GOOGLE_CLOUD_LOCATION:
            raise RuntimeError("缺少 GOOGLE_CLOUD_LOCATION")

        return genai.Client(
            vertexai=True,
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
            credentials=credentials,
        )

    async def transcribe_upload_file(
        self,
        file: UploadFile,
    ) -> dict:
        try:
            if not settings.GEMINI_MODEL_NAME:
                return {
                    "text": "Gemini Speech 設定不存在，請確認 GEMINI_MODEL_NAME",
                    "language": "zh-TW",
                }

            content = await file.read()

            if not content:
                return {
                    "text": "沒有收到音訊檔案",
                    "language": "zh-TW",
                }

            if len(content) < 2000:
                return {
                    "text": "音訊資料過短，無法辨識語音內容",
                    "language": "zh-TW",
                }

            mime_type = file.content_type or "audio/wav"

            print("收到 Gemini STT 音訊大小:", len(content), "bytes")
            print("content_type:", mime_type)

            prompt = """
你是一個語音辨識服務。請將音訊內容轉換成文字，並判斷語言。

只允許判斷以下四種語言：
- zh-TW：繁體中文 / 台灣中文
- en-US：英文
- ja-JP：日文
- ko-KR：韓文

請嚴格回傳 JSON，不要輸出 Markdown，不要輸出 ```json，不要輸出任何解釋。

JSON 格式如下：
{
  "text": "辨識出的逐字稿，請自動加上標點符號",
  "language": "zh-TW"
}

規則：
1. 如果語音是中文，language 請回傳 "zh-TW"，文字請使用繁體中文與台灣用語。
2. 如果語音是英文，language 請回傳 "en-US"。
3. 如果語音是日文，language 請回傳 "ja-JP"。
4. 如果語音是韓文，language 請回傳 "ko-KR"。
5. 如果沒有偵測到人聲或無法辨識，請回傳：
{
  "text": "無法辨識語音內容",
  "language": "zh-TW"
}
6. language 不可以回傳 zh-Hant、zh、en、ja、ko 或其他格式。
"""

            response = self.client.models.generate_content(
                model=settings.GEMINI_MODEL_NAME,
                contents=[
                    prompt,
                    types.Part.from_bytes(
                        data=content,
                        mime_type=mime_type,
                    ),
                ],
            )

            raw_text = response.text.strip() if response.text else ""
            print("Gemini STT raw response:", raw_text)

            result = self._parse_gemini_result(raw_text)

            print("Gemini STT 完整辨識結果:", result["text"])
            print("Gemini STT 偵測語言:", result["language"])

            return result

        except Exception as e:
            return {
                "text": f"Gemini Speech 系統錯誤：{str(e)}",
                "language": "zh-TW",
            }

    def _parse_gemini_result(self, raw_text: str) -> dict:
        allowed_languages = {"zh-TW", "en-US", "ja-JP", "ko-KR"}

        if not raw_text:
            return {
                "text": "無法辨識語音內容",
                "language": "zh-TW",
            }

        cleaned = (
            raw_text
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        try:
            data = json.loads(cleaned)

            text = str(data.get("text", "")).strip()
            language = str(data.get("language", "zh-TW")).strip()

            if language not in allowed_languages:
                language = "zh-TW"

            if not text:
                text = "無法辨識語音內容"

            return {
                "text": text,
                "language": language,
            }

        except Exception:
            return {
                "text": cleaned if cleaned else "無法辨識語音內容",
                "language": "zh-TW",
            }


gemini_speech_to_text_service = GeminiSpeechToTextService()