"""Common record schema shared by every dataset loader.

    text          str            the raw message
    label_binary  int            1 = scam / spam, 0 = legitimate (ham)
    category      str | None     one of ml.templates.ALL_CATEGORIES, or None when the source
                                 only has a binary label (all real datasets)
    source        str            dataset name, e.g. "synthetic", "uci_sms_spam"
    split         str            "train" | "val" | "test"
    group         str            grouping key (template id for synthetic rows) - rows sharing a
                                 group never cross splits
"""
from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Iterable, TypedDict

BACKEND = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MANIFEST = DATA_DIR / "manifest.json"

FIELDS = ["text", "label_binary", "category", "source", "split", "group"]
SPLITS = ("train", "val", "test")


class Record(TypedDict):
    text: str
    label_binary: int
    category: str | None
    source: str
    split: str
    group: str


def validate(rows: Iterable[Record]) -> None:
    from ..templates import ALL_CATEGORIES

    for i, r in enumerate(rows):
        if not isinstance(r["text"], str) or not r["text"].strip():
            raise ValueError(f"row {i}: empty text")
        if r["label_binary"] not in (0, 1):
            raise ValueError(f"row {i}: label_binary must be 0/1")
        if r["category"] is not None and r["category"] not in ALL_CATEGORIES:
            raise ValueError(f"row {i}: unknown category {r['category']}")
        if r["split"] not in SPLITS:
            raise ValueError(f"row {i}: bad split {r['split']}")


def write_csv(rows: list[Record], path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({**r, "category": r["category"] or ""})
    return sha256_file(path)


def read_csv(path: Path) -> list[Record]:
    with path.open(encoding="utf-8") as f:
        return [
            Record(text=r["text"], label_binary=int(r["label_binary"]), category=r["category"] or None,
                   source=r["source"], split=r["split"], group=r["group"])
            for r in csv.DictReader(f)
        ]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_WS = re.compile(r"\s+")


def dedup_key(text: str) -> str:
    """Key used to detect duplicate messages (case/whitespace-insensitive)."""
    return _WS.sub(" ", text.strip().lower())


def counts(rows: list[Record]) -> dict:
    out: dict = {"total": len(rows)}
    for s in SPLITS:
        part = [r for r in rows if r["split"] == s]
        if part:
            out[s] = {"rows": len(part), "positive": sum(r["label_binary"] for r in part)}
    return out
