from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.errors import DuplicateKeyError

from ..db import get_db
from ..schemas import ReportIn
from ..security import current_user
from ..services import identifiers
from ..services.community import report_summary

router = APIRouter(prefix="/api/reports", tags=["reports"])


def serialize(d: dict) -> dict:
    return {"id": str(d["_id"]), "kind": d["kind"], "value": d["value"], "category": d["category"],
            "note": d.get("note"), "created_at": d["created_at"].isoformat()}


@router.post("", status_code=201)
async def create_report(body: ReportIn, user: dict = Depends(current_user)):
    value = identifiers.normalize(body.kind, body.value)
    if not value:
        raise HTTPException(422, f"That does not look like a valid {body.kind}")
    doc = {"user_id": user["_id"], "kind": body.kind, "value": value, "category": body.category,
           "note": (body.note or "").strip() or None, "created_at": datetime.now(timezone.utc)}
    try:
        res = await get_db().reports.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "You have already reported this")
    doc["_id"] = res.inserted_id
    return serialize(doc) | {"summary": await report_summary(body.kind, value)}


@router.get("")
async def my_reports(user: dict = Depends(current_user), limit: int = Query(20, ge=1, le=50),
                     cursor: str | None = None):
    q: dict = {"user_id": user["_id"]}
    if cursor:
        try:
            q["_id"] = {"$lt": ObjectId(cursor)}
        except InvalidId:
            raise HTTPException(422, "Bad cursor")
    docs = await get_db().reports.find(q).sort("_id", -1).limit(limit + 1).to_list(limit + 1)
    more = len(docs) > limit
    docs = docs[:limit]
    # attach global counts for the page in one aggregation
    pairs = [{"kind": d["kind"], "value": d["value"]} for d in docs]
    counts = {}
    if pairs:
        async for r in get_db().reports.aggregate([
            {"$match": {"$or": pairs}},
            {"$group": {"_id": {"k": "$kind", "v": "$value"}, "n": {"$sum": 1}}},
        ]):
            counts[(r["_id"]["k"], r["_id"]["v"])] = r["n"]
    return {"items": [serialize(d) | {"total_reports": counts.get((d["kind"], d["value"]), 1)} for d in docs],
            "next_cursor": str(docs[-1]["_id"]) if more else None}


@router.delete("/{report_id}", status_code=204)
async def delete_report(report_id: str, user: dict = Depends(current_user)):
    try:
        oid = ObjectId(report_id)
    except InvalidId:
        raise HTTPException(404, "Report not found")
    res = await get_db().reports.delete_one({"_id": oid, "user_id": user["_id"]})
    if not res.deleted_count:
        raise HTTPException(404, "Report not found")


@router.get("/top")
async def top_reported(user: dict = Depends(current_user), limit: int = Query(8, ge=1, le=25)):
    return {"items": await top_identifiers(limit)}


async def top_identifiers(limit: int) -> list[dict]:
    pipeline = [
        {"$group": {"_id": {"kind": "$kind", "value": "$value"}, "reports": {"$sum": 1},
                    "categories": {"$push": "$category"}, "last": {"$max": "$created_at"}}},
        {"$sort": {"reports": -1, "last": -1}},
        {"$limit": limit},
    ]
    out = []
    async for r in get_db().reports.aggregate(pipeline):
        cats = r["categories"]
        out.append({"kind": r["_id"]["kind"], "value": r["_id"]["value"], "reports": r["reports"],
                    "category": max(set(cats), key=cats.count), "last_reported": r["last"].isoformat()})
    return out
