from enum import Enum


class TtsType(str, Enum):
    GEMINI = "gemini"
    AZURE = "azure"