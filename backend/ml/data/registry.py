"""Build / load every dataset and keep data/manifest.json up to date.

    python -m ml.data.registry            # build all datasets that can be obtained
    python -m ml.data.registry --only synthetic_in uci_sms_spam

Processed files go to data/processed/<name>.csv (git-ignored); the manifest with source,
licence, sha256 and row counts is committed.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from . import scamspam, synthetic, uci
from .schema import MANIFEST, PROCESSED_DIR, Record, counts, dedup_key, read_csv, sha256_file, write_csv

DATASETS = {synthetic.NAME: synthetic, uci.NAME: uci, scamspam.NAME: scamspam}


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"datasets": {}}


def build(name: str) -> list[Record]:
    mod = DATASETS[name]
    if name == scamspam.NAME:
        rows = mod.build(exclude={dedup_key(r["text"]) for r in load(uci.NAME)})
    else:
        rows = mod.build()
    path = PROCESSED_DIR / f"{name}.csv"
    digest = write_csv(rows, path)
    entry = dict(mod.INFO)
    raw = getattr(mod, "RAW_FILE", None)
    entry.update({
        "raw_sha256": sha256_file(raw) if raw is not None and raw.exists() else None,
        "processed_file": f"data/processed/{name}.csv",
        "processed_sha256": digest,
        "counts": counts(rows),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    m = _manifest()
    m["datasets"][name] = entry
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=2) + "\n")
    return rows


def load(name: str, build_missing: bool = True) -> list[Record]:
    path = PROCESSED_DIR / f"{name}.csv"
    if not path.exists():
        if not build_missing:
            raise FileNotFoundError(f"{path} missing - run `python -m ml.data.registry --only {name}`")
        return build(name)
    return read_csv(path)


def info(name: str) -> dict:
    """Manifest entry (with the hash of the processed file currently on disk)."""
    entry = dict(_manifest()["datasets"].get(name, DATASETS[name].INFO))
    path = PROCESSED_DIR / f"{name}.csv"
    if path.exists():
        entry["processed_sha256"] = sha256_file(path)
    return entry


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=list(DATASETS))
    args = ap.parse_args()
    for name in args.only:
        try:
            rows = build(name)
            print(f"{name}: {counts(rows)}")
        except Exception as e:  # network failures are reported, not fatal
            print(f"{name}: NOT BUILT ({type(e).__name__}: {e}) - dataset required before evaluation")


if __name__ == "__main__":
    main()
