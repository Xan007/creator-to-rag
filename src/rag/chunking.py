"""Deterministic chunking for long creator sources.

Short social posts stay as one chunk. Longer transcripts, lessons and documents
are split on paragraph/section boundaries so retrieval can cite a useful unit.
"""

import re
from typing import List


DEFAULT_CHUNK_SIZE = 1200
DEFAULT_OVERLAP = 180


def chunk_text(text: str, max_chars: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    if max_chars <= 0 or overlap < 0 or overlap >= max_chars:
        raise ValueError("max_chars must be positive and overlap must be smaller than max_chars")

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    chunks: List[str] = []
    current = ""
    for paragraph in paragraphs or [text]:
        while len(paragraph) > max_chars:
            prefix = paragraph[:max_chars].strip()
            if current:
                chunks.append(current)
                current = ""
            chunks.append(prefix)
            paragraph = paragraph[max_chars - overlap :].lstrip()
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            tail = current[-overlap:] if overlap and current else ""
            current = f"{tail}\n{paragraph}".strip()
    if current:
        chunks.append(current)
    return chunks
