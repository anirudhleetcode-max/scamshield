"""Text normalisation shared by training and inference.

`normalize` is LENGTH-PRESERVING (same number of characters in and out), so a
character offset in the normalised text is the same offset in the user's
original message. That is what lets us map n-gram weights back onto the
original text for highlighting.
"""
import re

WORD_TOKEN_PATTERN = r"(?u)\b\w\w+\b"
WORD_RE = re.compile(WORD_TOKEN_PATTERN)


def normalize(text: str) -> str:
    out = []
    for ch in text:
        if ch.isdigit():
            out.append("0")  # amounts, OTPs, phone numbers -> shape only
        else:
            low = ch.lower()
            out.append(low if len(low) == 1 else ch)
    return "".join(out)
