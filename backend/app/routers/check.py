import re
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from ml.templates import ALL_CATEGORIES, CATEGORY_LABELS

from ..db import get_db
from ..schemas import CheckIn
from ..security import current_user
from ..services import identifiers
from ..services.analyzer import analyze
from ..services.community import report_counts

router = APIRouter(prefix="/api", tags=["check"])


async def run_analysis(body: CheckIn) -> dict:
    # cheap regex pass first so community counts can be fetched in one aggregation
    pairs = [(i["kind"], i["value"]) for i in identifiers.extract(body.text)]
    counts = await report_counts(pairs)
    return await run_in_threadpool(analyze, body.text, body.sender, counts)


def _oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(404, "Not found")


def serialize(doc: dict, full: bool = False) -> dict:
    out = {
        "id": str(doc["_id"]),
        "text": doc["text"],
        "sender": doc.get("sender"),
        "score": doc["score"],
        "verdict": doc["verdict"],
        "category": doc["category"],
        "category_label": doc["result"]["category_label"],
        "flags_hit": doc.get("flags_hit", []),
        "created_at": doc["created_at"].isoformat(),
    }
    if full:
        out["result"] = doc["result"]
    return out


@router.post("/check/analyze")
async def analyze_live(body: CheckIn, user: dict = Depends(current_user)):
    """Analyse without saving (used for live analysis while typing)."""
    return await run_analysis(body)


@router.post("/checks", status_code=201)
async def create_check(body: CheckIn, user: dict = Depends(current_user)):
    result = await run_analysis(body)
    doc = {
        "user_id": user["_id"],
        "text": body.text,
        "sender": body.sender,
        "score": result["score"],
        "verdict": result["verdict"],
        "category": result["category"],
        "flags_hit": [f["id"] for f in result["flags"] if f["hit"]],
        "identifiers": [{"kind": i["kind"], "value": i["value"]} for i in result["identifiers"]],
        "result": result,
        "created_at": datetime.now(timezone.utc),
    }
    res = await get_db().checks.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc, full=True)


@router.get("/checks")
async def list_checks(
    user: dict = Depends(current_user),
    limit: int = Query(20, ge=1, le=50),
    cursor: str | None = None,
    verdict: str | None = Query(None, pattern="^(Safe|Suspicious|Scam)$"),
    category: str | None = None,
    q: str | None = Query(None, max_length=80),
):
    if category and category not in ALL_CATEGORIES:
        raise HTTPException(422, "Unknown category")
    base: dict = {"user_id": user["_id"]}
    if verdict:
        base["verdict"] = verdict
    if category:
        base["category"] = category
    if q and q.strip():
        base["text"] = {"$regex": re.escape(q.strip()), "$options": "i"}
    page = dict(base)
    if cursor:
        page["_id"] = {"$lt": _oid(cursor)}
    db = get_db()
    docs = await db.checks.find(page, {"result": 0}).sort("_id", -1).limit(limit + 1).to_list(limit + 1)
    has_more = len(docs) > limit
    docs = docs[:limit]
    total = await db.checks.count_documents(base)
    items = []
    for d in docs:
        d["result"] = {"category_label": CATEGORY_LABELS.get(d["category"], d["category"])}
        items.append(serialize(d))
    return {"items": items, "next_cursor": str(docs[-1]["_id"]) if has_more else None, "total": total}


@router.get("/checks/{check_id}")
async def get_check(check_id: str, user: dict = Depends(current_user)):
    doc = await get_db().checks.find_one({"_id": _oid(check_id), "user_id": user["_id"]})
    if not doc:
        raise HTTPException(404, "Check not found")
    return serialize(doc, full=True)


@router.delete("/checks/{check_id}", status_code=204)
async def delete_check(check_id: str, user: dict = Depends(current_user)):
    res = await get_db().checks.delete_one({"_id": _oid(check_id), "user_id": user["_id"]})
    if not res.deleted_count:
        raise HTTPException(404, "Check not found")
