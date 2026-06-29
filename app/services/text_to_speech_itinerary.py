import os
import json
from app.core.config import settings
from google.cloud import texttospeech


credentials_json_str = settings.GOOGLE_CREDENTIALS_JSON
gcp_credentials = None

if credentials_json_str:
    try:
        credentials_info = json.loads(credentials_json_str)
        from google.oauth2 import service_account
        gcp_credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
    except Exception as e:
        print(f"❌ 解析 GCP 憑證環境變數失敗: {e}")
else:
    print("⚠️ 未找到 GCP 憑證環境變數，若需使用 Vertex AI 可能會發生驗證錯誤。")

# 2. 檢查 SDK 載入
try:
    from google import genai
    from google.genai import types
    HAS_GENAI_SDK = True
except ImportError:
    HAS_GENAI_SDK = False

# 定義合法的語系清單 
SUPPORTED_LANGUAGES = [
    "en", "en-US", "zh-Hant", "zh-TW", "zh", "cmn-TW", 
    "ko", "ko-KR", "ja", "ja-JP", 
    "vi", "vi-VN", "th", "th-TH", "id", "id-ID", 
    "fr", "fr-FR", "de", "de-DE", "es", "es-ES", "pt", "pt-PT", "it", "it-IT"
]

def text_to_speech(
    text: str, 
    language: str = "zh-TW",
    speaking_rate: float = 1.15, # 🚀 新增：預設語速設為 1.15 倍速，比普通說話更乾淨俐落
    pitch: float = 1.0           # 🚀 新增：預設音高微升 +1.0 半音，聲音更甜美、親切有朝氣
) -> bytes | None:
    """
    將文字轉換為語音 (使用 Google Cloud TTS)
    根據語系動態切換：中文用 cmn-TW-Wavenet-A，外語統一用 en-US-Wavenet-F
    並且微調語速與語氣音高
    """
    if language not in SUPPORTED_LANGUAGES:
        print(f"❌ [TTS 錯誤] Refused Speech Synthesis: {language} is not supported.")
        return None
    
    try:
        if gcp_credentials:
            client = texttospeech.TextToSpeechClient(credentials=gcp_credentials)
        else:
            print("⚠️ 警告：未偵測到 gcp_credentials，將嘗試退回使用預設環境變數連線。")
            client = texttospeech.TextToSpeechClient()
        
        synthesis_input = texttospeech.SynthesisInput(text=text)

        chinese_codes = ["zh", "zh-TW", "zh-Hant", "zh-Hans", "cmn-TW"]

        # 分流並挑選最合適的優雅女聲音色
        if language in chinese_codes:
            print(f"📍 [TTS 路由] 中文 ({language}) -> cmn-TW-Wavenet-A")
            voice = texttospeech.VoiceSelectionParams(
                language_code="cmn-TW", 
                name="cmn-TW-Wavenet-A"  
            )
        else:
            print(f"📍 [TTS 路由] 外語 ({language}) -> en-US-Wavenet-F")
            voice = texttospeech.VoiceSelectionParams(
                language_code="en-US", 
                name="en-US-Wavenet-F"   
            )
        
        # 🚀 核心修改：在 AudioConfig 中注入語速與語氣音調微調
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=speaking_rate, # 語速 (0.25 - 4.0)
            pitch=pitch                  # 音高/語調偏好 (-20.0 - 20.0)
        )

        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        
        print(f"✅ Speech synthesis success (Google TTS) - Speed: {speaking_rate}, Pitch: {pitch}")
        return response.audio_content

    except Exception as e:
        print(f"❌ [TTS 錯誤] Speech synthesis failed: {e}")
        return None