import os
from openai import AzureOpenAI
from app.core.config import settings

def text_to_speech(text: str, language: str = "zh-TW") -> bytes | None:
    """
    將文字轉換為語音 (使用 Azure OpenAI TTS)
    參考來源: app.py 的 azure_speech 實作
    """
    # 1. 從環境變數 (settings) 取得金鑰與端點
    tts_key = getattr(settings, "AZURE_OPENAI_TTS_KEY", None)
    tts_url = getattr(settings, "AZURE_OPENAI_TTS_URL", None)

    # 檢查是否缺少設定
    if not tts_key or not tts_url:
        print("❌ [TTS 錯誤] 找不到 azure_openai_tts_key 或 azure_openai_tts_url")
        raise RuntimeError("Azure OpenAI TTS 相關金鑰或端點尚未設定")

    try:
        # 2. 建立 Azure OpenAI 客戶端
        client = AzureOpenAI(
            api_key=tts_key,
            api_version="2024-02-15-preview",
            azure_endpoint=tts_url
        )

        # 3. 呼叫語音生成服務
        response = client.audio.speech.create(
            model="tts",   # 對應你在 Azure 後台設定的部署名稱
            voice="nova",  # nova 音色原生支援多國語言，所以這裡忽略 language 參數
            input=text
        )

        # 4. 成功回傳 MP3 二進位資料 (bytes)
        print(f"✅ Speech synthesis success (Azure OpenAI) - Text preview: {text[:10]}...")
        return response.content

    except Exception as e:
        # 捕捉並印出錯誤，避免 500 錯誤被吞掉
        print(f"❌ [TTS 錯誤] Speech synthesis failed: {e}")
        return None