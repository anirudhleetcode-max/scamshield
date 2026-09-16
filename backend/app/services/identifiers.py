"""Find and normalise phone numbers, UPI IDs and URLs inside free text."""
from __future__ import annotations

import re
from urllib.parse import unquote

PHONE_RE = re.compile(r"(?<![\w@])(?:\+?91[\s-]?|0)?([6-9]\d{4})[\s-]?(\d{5})(?![\w@])")
UPI_ID_RE = re.compile(r"(?<![\w.\-])([a-zA-Z0-9][\w.\-]{1,63}@[a-zA-Z][a-zA-Z0-9]{1,31})(?![\w.@]*\.[a-zA-Z])")
UPI_LINK_RE = re.compile(r"upi://pay\?[^\s]+", re.I)
URL_RE = re.compile(
    r"(?:(?:https?://)[^\s<>\"']+)"  # explicit scheme
    r"|(?:\b(?:www\.)?[a-z0-9][a-z0-9\-]*(?:\.[a-z0-9\-]+)*\.(?:[a-z]{2,10})(?:/[^\s<>\"']*)?)",
    re.I,
)
# bare "word.word" false positives: only accept scheme-less hosts with a known-ish TLD
BARE_TLDS = {"com", "in", "net", "org", "co", "xyz", "top", "click", "live", "info", "buzz", "icu", "shop",
             "online", "site", "ly", "gy", "at", "is", "me", "io", "app", "sbi", "cc", "vip", "tk", "ml", "ga", "cf", "gov"}


def norm_phone(value: str) -> str | None:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        return digits
    return None


def norm_upi(value: str) -> str:
    return value.strip().lower()


def norm_url(value: str) -> str:
    v = unquote(value.strip()).lower()
    v = re.sub(r"^https?://", "", v)
    v = re.sub(r"^www\.", "", v)
    return v.rstrip("/.,)")


def detect_kind(value: str) -> str:
    v = value.strip()
    if v.lower().startswith("upi://"):
        return "upi_link"
    if norm_phone(v) and re.fullmatch(r"[\d\s+\-()]+", v):
        return "phone"
    if re.fullmatch(r"[\w.\-]+@[a-zA-Z][a-zA-Z0-9]*", v):
        return "upi"
    return "url"


def normalize(kind: str, value: str) -> str | None:
    if kind == "phone":
        return norm_phone(value)
    if kind == "upi":
        v = norm_upi(value)
        return v if re.fullmatch(r"[\w.\-]{2,64}@[a-z][a-z0-9]{1,31}", v) else None
    if kind == "url":
        v = norm_url(value)
        return v if "." in v and " " not in v and len(v) <= 500 else None
    return None


def extract(text: str) -> list[dict]:
    """Return [{kind, value (normalised), raw, start, end}] without overlaps."""
    found: list[dict] = []
    taken: list[tuple[int, int]] = []

    def add(kind, raw, s, e, value):
        if value and not any(s < te and e > ts for ts, te in taken):
            taken.append((s, e))
            found.append({"kind": kind, "value": value, "raw": raw, "start": s, "end": e})

    for m in UPI_LINK_RE.finditer(text):
        add("upi_link", m.group(), m.start(), m.end(), m.group())
    for m in UPI_ID_RE.finditer(text):
        add("upi", m.group(1), m.start(1), m.end(1), norm_upi(m.group(1)))
    for m in URL_RE.finditer(text):
        raw = m.group().rstrip(".,)!")
        if not raw.lower().startswith("http"):
            host = raw.split("/")[0]
            if host.rsplit(".", 1)[-1].lower() not in BARE_TLDS or "@" in text[max(0, m.start() - 1):m.start()]:
                continue
        add("url", raw, m.start(), m.start() + len(raw), norm_url(raw))
    for m in PHONE_RE.finditer(text):
        add("phone", m.group(), m.start(), m.end(), m.group(1) + m.group(2))
    return sorted(found, key=lambda d: d["start"])
