import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

from ml.templates import CATEGORY_LABELS

from ..config import get_settings
from ..db import get_db
from ..security import current_user
from ..services.classifier import artifact_paths, get_model, model_status
from .reports import top_identifiers

router = APIRouter(prefix="/api", tags=["insights"])
TZ = "Asia/Kolkata"


@router.get("/insights")
async def insights(user: dict = Depends(current_user), days: int = Query(30, ge=7, le=90)):
    now = datetime.now(timezone.utc)
    since = (now.astimezone(ZoneInfo(TZ)) - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    pipeline = [
        {"$match": {"user_id": user["_id"], "created_at": {"$gte": since}}},
        {"$facet": {
            "per_day": [
                {"$group": {"_id": {"day": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at", "timezone": TZ}},
                                    "verdict": "$verdict"}, "n": {"$sum": 1}}},
            ],
            "categories": [
                {"$group": {"_id": "$category", "n": {"$sum": 1}, "avg_score": {"$avg": "$score"}}},
                {"$sort": {"n": -1}},
            ],
            "totals": [
                {"$group": {"_id": None, "total": {"$sum": 1},
                            "flagged": {"$sum": {"$cond": [{"$ne": ["$verdict", "Safe"]}, 1, 0]}},
                            "scam": {"$sum": {"$cond": [{"$eq": ["$verdict", "Scam"]}, 1, 0]}},
                            "abstained": {"$sum": {"$cond": [{"$eq": ["$status", "insufficient_confidence"]}, 1, 0]}},
                            "demo": {"$sum": {"$cond": [{"$eq": ["$demo", True]}, 1, 0]}},
                            "avg_score": {"$avg": "$score"}}},
            ],
            "flags": [
                {"$unwind": "$flags_hit"},
                {"$group": {"_id": "$flags_hit", "n": {"$sum": 1}}},
                {"$sort": {"n": -1}},
            ],
        }},
    ]
    facet = (await get_db().checks.aggregate(pipeline).to_list(1))[0]

    # dense day series (the aggregation only returns days that have data)
    by_day: dict[str, dict] = {}
    for row in facet["per_day"]:
        by_day.setdefault(row["_id"]["day"], {})[row["_id"]["verdict"]] = row["n"]
    series = []
    for i in range(days):
        d = (since + timedelta(days=i)).strftime("%Y-%m-%d")
        v = by_day.get(d, {})
        series.append({"date": d, "Safe": v.get("Safe", 0), "Suspicious": v.get("Suspicious", 0), "Scam": v.get("Scam", 0)})

    t = facet["totals"][0] if facet["totals"] else {"total": 0, "flagged": 0, "scam": 0, "avg_score": None,
                                                     "abstained": 0, "demo": 0}
    my_reports = await get_db().reports.count_documents({"user_id": user["_id"]})
    return {
        "days": days,
        "per_day": series,
        "categories": [{"category": c["_id"], "label": CATEGORY_LABELS.get(c["_id"], c["_id"]), "n": c["n"],
                        "avg_score": round(c["avg_score"] or 0)} for c in facet["categories"]],
        "totals": {"checks": t["total"], "flagged": t["flagged"], "scam": t["scam"],
                   "flagged_share": round(t["flagged"] / t["total"], 3) if t["total"] else 0.0,
                   "avg_score": round(t["avg_score"]) if t["avg_score"] is not None else None,
                   "my_reports": my_reports, "abstained": t["abstained"], "demo_checks": t["demo"]},
        "flags": [{"id": f["_id"], "n": f["n"]} for f in facet["flags"]],
        "top_reported": await top_identifiers(8),
    }


@router.get("/model")
async def model_info():
    """Model card of the loaded artifact (public, no user data)."""
    status = model_status()
    card = None
    if status["loaded"]:
        card = get_model().card
    else:
        s = get_settings()
        _, card_path = artifact_paths(s.model_version, Path(s.model_dir))
        if card_path.exists():
            card = json.loads(card_path.read_text())
    if card is None:
        return {"available": False, "loaded": False, "error": status["error"], "card": None}
    main = card["metrics"]["main_model_test"]
    cat = card["metrics"].get("category_head_test", {}).get("synthetic_test", {})
    return {
        "available": True,
        "loaded": status["loaded"],
        "error": status["error"],
        "model_version": card["model_version"],
        # legacy summary fields (kept for older clients)
        "dataset": {"total": card["training_data"]["train_rows"] + card["training_data"]["val_rows"],
                    "train": card["training_data"]["train_rows"], "val": card["training_data"]["val_rows"],
                    "contains_synthetic": card["training_data"]["contains_synthetic"]},
        "heldout_binary": main.get("synthetic_test"),
        "heldout_category": cat or None,
        "naive_random_split": None,
        "card": card,
    }
