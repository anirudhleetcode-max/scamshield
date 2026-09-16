"""Community report lookups (async, Mongo)."""
from ..db import get_db


async def report_counts(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], int]:
    """Distinct reporters per (kind, value). The unique (user_id, kind, value) index means
    one document == one user, so counting documents counts distinct users."""
    pairs = list({p for p in pairs if p[1]})
    if not pairs:
        return {}
    pipeline = [
        {"$match": {"$or": [{"kind": k, "value": v} for k, v in pairs]}},
        {"$group": {"_id": {"kind": "$kind", "value": "$value"}, "n": {"$sum": 1}}},
    ]
    out = {}
    async for row in get_db().reports.aggregate(pipeline):
        out[(row["_id"]["kind"], row["_id"]["value"])] = row["n"]
    return out


async def report_summary(kind: str, value: str) -> dict:
    pipeline = [
        {"$match": {"kind": kind, "value": value}},
        {"$group": {"_id": "$category", "n": {"$sum": 1}, "last": {"$max": "$created_at"}}},
        {"$sort": {"n": -1}},
    ]
    rows = [r async for r in get_db().reports.aggregate(pipeline)]
    return {
        "count": sum(r["n"] for r in rows),
        "categories": [{"category": r["_id"], "n": r["n"]} for r in rows],
        "last_reported": max((r["last"] for r in rows), default=None),
    }
