"""Run one experiment config and record everything needed to reproduce it.

    python experiments/run.py --config experiments/configs/combined.json

Results go to experiments/results/<name>-<UTC timestamp>/ :
metrics.json, config.json, env.json (git commit, library versions), summary.md, errors_*.csv
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ml.experiment import run_experiment, write_run  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "experiments" / "results")
    args = ap.parse_args()
    cfg = json.loads(args.config.read_text())
    run_id = f"{cfg['name']}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    out = args.out / run_id
    res = run_experiment(cfg, out)
    write_run(cfg, res, out)
    print(f"wrote {out.relative_to(ROOT)} in {res['seconds']}s")


if __name__ == "__main__":
    main()
