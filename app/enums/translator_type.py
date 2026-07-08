from enum import Enum


class TranslatorType(str, Enum):
    AZURE = "azure"
    GOOGLE = "google"