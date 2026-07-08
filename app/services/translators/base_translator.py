from abc import ABC, abstractmethod


class BaseTranslator(ABC):

    @abstractmethod
    def normalize_language(self, language: str | None) -> str:
        pass

    @abstractmethod
    def detect_language(self, text: str) -> str:
        pass

    @abstractmethod
    def translate(
        self,
        text: str,
        target_language: str,
        source_language: str | None = None,
    ) -> str:
        pass

    @abstractmethod
    def translate_batch(
        self,
        texts: list[str],
        target_language: str,
        source_language: str | None = None,
    ) -> list[str]:
        pass