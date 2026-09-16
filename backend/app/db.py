from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from .config import get_settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(get_settings().mongo_uri, serverSelectionTimeoutMS=4000, tz_aware=True)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[get_settings().mongo_db]


async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


async def ensure_indexes() -> None:
    db = get_db()
    await db.users.create_index("email", unique=True)
    # history: newest first per user, optionally filtered by verdict / category
    await db.checks.create_index([("user_id", ASCENDING), ("_id", DESCENDING)])
    await db.checks.create_index([("user_id", ASCENDING), ("verdict", ASCENDING), ("_id", DESCENDING)])
    await db.checks.create_index([("user_id", ASCENDING), ("category", ASCENDING), ("_id", DESCENDING)])
    await db.checks.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    # one report per user per identifier; lookups by identifier
    await db.reports.create_index([("user_id", ASCENDING), ("kind", ASCENDING), ("value", ASCENDING)],
                                  unique=True, name="uniq_user_identifier")
    await db.reports.create_index([("kind", ASCENDING), ("value", ASCENDING)])
    await db.reports.create_index([("user_id", ASCENDING), ("_id", DESCENDING)])
