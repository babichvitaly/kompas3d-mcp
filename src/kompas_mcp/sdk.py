"""Read the installed SDK archive without extracting or executing its HTML."""

import html
import os
import re
from pathlib import Path
from zipfile import ZipFile


def sdk_archive() -> Path:
    root = os.getenv("KOMPAS_SDK_PATH")
    roots = (
        [Path(root)]
        if root
        else sorted(Path("C:/Program Files/ASCON").glob("KOMPAS*/SDK"), reverse=True)
    )
    for folder in roots:
        files = sorted((folder / "Help").glob("KOMPAS_SDK*.zip"))
        if files:
            return files[0]
    raise FileNotFoundError("SDK Help archive not found; set KOMPAS_SDK_PATH")


def search(query: str, limit: int = 30) -> dict:
    if not query.strip() or not 1 <= limit <= 100:
        raise ValueError("Provide a topic/interface/member substring and limit 1..100")
    with ZipFile(sdk_archive()) as archive:
        matches = sorted(
            n for n in archive.namelist() if n.endswith(".html") and query.lower() in n.lower()
        )
    return {"total": len(matches), "topics": matches[:limit]}


def read(topic: str, offset: int = 0, length: int = 16000) -> dict:
    if offset < 0 or not 1 <= length <= 30000:
        raise ValueError("offset must be nonnegative; length must be 1..30000")
    with ZipFile(sdk_archive()) as archive:
        if topic not in archive.namelist() or not topic.endswith(".html"):
            raise ValueError("Use an exact topic returned by sdk_search")
        markup = archive.read(topic).decode("utf-8-sig")
    markup = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", markup, flags=re.DOTALL | re.IGNORECASE)
    links = re.findall(r'href="([^"#]+\.html)(?:#[^"]*)?"', markup)
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", markup))).strip()
    return {
        "topic": topic,
        "text": text[offset : offset + length],
        "total_chars": len(text),
        "links": sorted(set(links)),
    }
