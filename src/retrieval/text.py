from __future__ import annotations

import re


TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "i", "in", "is", "it", "me", "my", "of", "on", "or", "please", "some",
    "that", "the", "this", "to", "want", "with", "would", "you", "looking",
}


def terms(text: str) -> list[str]:
    return [
        value.lower() for value in TOKEN_RE.findall(text)
        if len(value) > 1 and value.lower() not in STOPWORDS
    ]
