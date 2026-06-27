import re


def markdown_to_text(markdown_text: str | None) -> str:
    if not markdown_text:
        return ""

    text = markdown_text

    # 移除粗體、斜體
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)
    text = re.sub(r"_(.*?)_", r"\1", text)

    # 移除標題符號
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)

    # 移除清單符號
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)

    # 移除 inline code / code block 符號
    text = text.replace("```", "")
    text = text.replace("`", "")

    # 移除 Markdown link，只保留文字
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # 換行轉成語音比較自然的停頓
    text = re.sub(r"\n{2,}", "。", text)
    text = re.sub(r"\n", "，", text)

    # 移除多餘空白
    text = re.sub(r"\s+", " ", text)

    return text.strip()