from enum import Enum


class SpeechType(str, Enum):
    AZURE = "azure"
    GEMINI = "gemini"