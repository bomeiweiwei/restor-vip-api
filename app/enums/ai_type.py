from enum import Enum


class AiType(str, Enum):
    GEMINI = "gemini"
    LMSTUDIO = "lmstudio"
    AZURE = "azure"