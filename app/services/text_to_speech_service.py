import os
import azure.cognitiveservices.speech as speechsdk

from app.core.config import settings

def text_to_speech(text: str, language: str = "zh-TW") -> bytes | None:
    speech_key = settings.AZURE_SPEECH_KEY
    speech_region = settings.AZURE_SPEECH_REGION

    if not speech_key or not speech_region:
        raise RuntimeError("AZURE_SPEECH_KEY 或 AZURE_SPEECH_REGION 尚未設定")

    speech_config = speechsdk.SpeechConfig(
        subscription=speech_key,
        region=speech_region,
    )

    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio16Khz64KBitRateMonoMp3
    )

    voice_map = {
        "zh-TW": "zh-TW-HsiaoChenNeural",
        "zh-Hant": "zh-TW-HsiaoChenNeural",

        "en-US": "en-US-JennyNeural",
        "en": "en-US-JennyNeural",

        "ja-JP": "ja-JP-NanamiNeural",
        "ja": "ja-JP-NanamiNeural",

        "ko-KR": "ko-KR-SunHiNeural",
        "ko": "ko-KR-SunHiNeural",
    }

    speech_config.speech_synthesis_voice_name = voice_map.get(
        language,
        "zh-TW-HsiaoChenNeural",
    )

    speech_synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=speech_config,
        audio_config=None,
    )

    result = speech_synthesizer.speak_text_async(text).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return result.audio_data

    if result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = result.cancellation_details

        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            raise RuntimeError(cancellation_details.error_details)

    return None