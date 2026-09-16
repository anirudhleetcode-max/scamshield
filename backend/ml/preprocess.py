"""Step 1 of the pipeline: text normalisation + input-quality signals.

`normalize` is LENGTH-PRESERVING: a character offset in the normalised text is the same
offset in the user's message, which is what lets explanations be mapped back onto the
original text. Digits become "0" so amounts / OTPs / phone numbers only contribute their
shape; letters are lower-cased (characters whose lower-case form has a different length,
e.g. "İ", are left alone).
"""
from __future__ import annotations

import re
import unicodedata

PREPROCESS_VERSION = "1.1"
WORD_TOKEN_PATTERN = r"(?u)\b\w\w+\b"
WORD_RE = re.compile(WORD_TOKEN_PATTERN)
URLISH_RE = re.compile(r"(?:https?://|www\.|upi://)\S+|\b[\w\-]+\.(?:com|in|xyz|top|ly|gy|co|net|org|info|live|click|site|online|sbi)(?:/\S*)?", re.I)


def normalize(text: str) -> str:
    out = []
    for ch in text:
        if ch.isdigit():
            out.append("0")
        else:
            low = ch.lower()
            out.append(low if len(low) == 1 else ch)
    return "".join(out)


def letter_stats(text: str) -> tuple[int, int]:
    """(letters, latin_letters). Latin = ASCII letters and Latin-1/Extended letters."""
    letters = latin = 0
    for ch in text:
        if ch.isalpha():
            letters += 1
            if ch.isascii() or "LATIN" in unicodedata.name(ch, ""):
                latin += 1
    return letters, latin


def quality_signals(text: str) -> dict:
    """Cheap facts about the input used by the abstention policy."""
    stripped = text.strip()
    words = WORD_RE.findall(stripped)
    letters, latin = letter_stats(stripped)
    url_chars = sum(len(m.group()) for m in URLISH_RE.finditer(stripped))
    non_space = len(re.sub(r"\s", "", stripped)) or 1
    return {
        "n_chars": len(stripped),
        "n_words": len(words),
        "letters": letters,
        "non_latin_ratio": round(1 - latin / letters, 3) if letters else 0.0,
        "url_ratio": round(url_chars / non_space, 3),
    }
