"""UCI SMS Spam Collection (REAL data, binary label only).

Almeida, T. & Hidalgo, J. (2011). SMS Spam Collection. UCI Machine Learning Repository.
https://doi.org/10.24432/C5CC84 - licensed CC BY 4.0.

5,574 English SMS (mostly UK/Singapore, 2000s) labelled ham / spam. "spam" here is
unsolicited commercial or premium-rate SMS, which is broader than our "scam" notion
(it includes plain marketing). We keep the dataset's binary label and set
category=None - no category is invented.

Exact duplicates (case/whitespace-insensitive) are removed BEFORE splitting so the same
message can never appear in both train and test. Split: stratified 70/15/15, seed 13.
"""
from __future__ import annotations

import urllib.request
import zipfile

from sklearn.model_selection import train_test_split

from .schema import RAW_DIR, Record, dedup_key, sha256_file, validate

NAME = "uci_sms_spam"
URL = "https://archive.ics.uci.edu/static/public/228/sms+spam+collection.zip"
RAW_FILE = RAW_DIR / "uci_sms_spam.zip"
SEED = 13

INFO = {
    "name": NAME,
    "version": "UCI id 228 (2011)",
    "kind": "real",
    "source_url": URL,
    "licence": "CC BY 4.0",
    "citation": "Almeida & Hidalgo (2011), SMS Spam Collection, UCI ML Repository, doi:10.24432/C5CC84",
    "description": "5,574 English SMS labelled ham/spam (UK + Singapore). Binary label only.",
    "labels": "label_binary only (spam=1); category is null",
    "split": "exact duplicates removed, then stratified 70/15/15 (seed 13)",
}


def download(timeout: int = 60) -> str:
    if not RAW_FILE.exists():
        RAW_FILE.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(URL, headers={"User-Agent": "scamshield-data/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            RAW_FILE.write_bytes(resp.read())
    return sha256_file(RAW_FILE)


def build() -> list[Record]:
    download()
    with zipfile.ZipFile(RAW_FILE) as z:
        raw = z.read("SMSSpamCollection").decode("utf-8", errors="replace")
    seen: set[str] = set()
    texts, labels = [], []
    for line in raw.splitlines():
        label, _, text = line.partition("\t")
        if label not in ("ham", "spam") or not text.strip():
            continue
        key = dedup_key(text)
        if key in seen:
            continue
        seen.add(key)
        texts.append(text)
        labels.append(int(label == "spam"))
    idx = list(range(len(texts)))
    tr, rest = train_test_split(idx, test_size=0.30, stratify=labels, random_state=SEED)
    va, te = train_test_split(rest, test_size=0.50, stratify=[labels[i] for i in rest], random_state=SEED)
    split = {**{i: "train" for i in tr}, **{i: "val" for i in va}, **{i: "test" for i in te}}
    rows = [Record(text=texts[i], label_binary=labels[i], category=None, source=NAME, split=split[i],
                   group=f"uci:{i}") for i in idx]
    validate(rows)
    return rows

