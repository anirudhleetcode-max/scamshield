"""FredZhang7/all-scam-spam (REAL data, binary label, OUT-OF-DOMAIN evaluation only).

https://huggingface.co/datasets/FredZhang7/all-scam-spam - Apache-2.0.
42,619 messages and emails in 43 languages (`is_spam`). Most rows are lower-cased,
space-tokenised emails (Enron / SpamAssassin style), so this is NOT an SMS dataset.

We use it only as a stress test: rows of <= 320 characters (message-like length), with
anything that duplicates a UCI SMS message removed. It is never used for training or
threshold tuning. All rows get split="test".
"""
from __future__ import annotations

import csv
import sys
import urllib.request

from .schema import RAW_DIR, Record, dedup_key, sha256_file, validate

NAME = "all_scam_spam_short"
URL = "https://huggingface.co/datasets/FredZhang7/all-scam-spam/resolve/main/junkmail_dataset.csv"
RAW_FILE = RAW_DIR / "all_scam_spam.csv"
MAX_CHARS = 320

INFO = {
    "name": NAME,
    "version": "HF main @ download time (sha256 below)",
    "kind": "real",
    "source_url": URL,
    "licence": "Apache-2.0",
    "description": "Multilingual spam/ham messages and emails; filtered to <= 320 chars and de-duplicated "
                   "against UCI. Mostly email fragments - an out-of-domain stress test, not an SMS benchmark.",
    "labels": "label_binary only (is_spam); category is null",
    "split": "all rows test (evaluation only)",
}


def download(timeout: int = 180) -> str:
    if not RAW_FILE.exists():
        RAW_FILE.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(URL, headers={"User-Agent": "scamshield-data/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp, RAW_FILE.open("wb") as out:
            while chunk := resp.read(1 << 20):
                out.write(chunk)
    return sha256_file(RAW_FILE)


def build(exclude: set[str] | None = None) -> list[Record]:
    download()
    exclude = exclude or set()
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    rows: list[Record] = []
    seen: set[str] = set()
    with RAW_FILE.open(encoding="utf-8", errors="replace", newline="") as f:
        for i, r in enumerate(csv.DictReader(f)):
            text = (r.get("text") or "").strip()
            if not text or len(text) > MAX_CHARS or r.get("is_spam") not in ("0", "1"):
                continue
            key = dedup_key(text)
            if key in seen or key in exclude:
                continue
            seen.add(key)
            rows.append(Record(text=text, label_binary=int(r["is_spam"]), category=None, source=NAME,
                               split="test", group=f"ass:{i}"))
    validate(rows)
    return rows
