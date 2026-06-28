import re


def clean_tts_text(text: str, max_chars: int = 300) -> str:
    if not text:
        return ""

    text = text.strip()

    # Markdown
    text = re.sub(r"[#*_`>\[\]\(\)]", "", text)

    # URL
    text = re.sub(r"https?://\S+", "", text)

    # 多個空白、換行
    text = re.sub(r"\s+", " ", text)

    # 避免過長
    if len(text) > max_chars:
        text = (
            text[:max_chars]
            .rstrip("，。、；：,. ")
            + "。詳細內容請查看畫面文字。"
        )

    return text