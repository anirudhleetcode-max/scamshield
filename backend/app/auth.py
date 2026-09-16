import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from pymongo.errors import DuplicateKeyError

from .config import get_settings
from .db import get_db
from .security import create_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def bcrypt_limit(cls, v: str) -> str:
        if len(v.encode()) > 72:
            raise ValueError("Password must be at most 72 bytes")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class LoginLimiter:
    """In-memory sliding window of failed logins per (client IP, email).
    Good enough for a single process; a multi-instance deployment would use Redis."""

    def __init__(self):
        self.failures: dict[tuple[str, str], deque] = defaultdict(deque)

    def _window(self, key) -> deque:
        s = get_settings()
        q = self.failures[key]
        while q and time.monotonic() - q[0] > s.login_window_s:
            q.popleft()
        return q

    def check(self, key) -> None:
        q = self._window(key)
        if len(q) >= get_settings().login_max_attempts:
            retry = int(get_settings().login_window_s - (time.monotonic() - q[0])) + 1
            raise HTTPException(429, "Too many failed sign-in attempts. Try again later.",
                                headers={"Retry-After": str(retry)})

    def fail(self, key) -> None:
        self._window(key).append(time.monotonic())

    def reset(self, key) -> None:
        self.failures.pop(key, None)


limiter = LoginLimiter()


def public_user(u: dict) -> dict:
    return {"id": str(u["_id"]), "name": u["name"], "email": u["email"], "is_demo": bool(u.get("is_demo", False))}


@router.post("/register", status_code=201)
async def register(body: RegisterIn):
    doc = {
        "name": body.name.strip(),
        "email": body.email.lower(),
        "password_hash": hash_password(body.password),
        "created_at": datetime.now(timezone.utc),
    }
    try:
        res = await get_db().users.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "An account with this email already exists")
    doc["_id"] = res.inserted_id
    return {"token": create_token(str(res.inserted_id)), "user": public_user(doc)}


@router.post("/login")
async def login(body: LoginIn, request: Request):
    key = (request.client.host if request.client else "?", body.email.lower())
    limiter.check(key)
    u = await get_db().users.find_one({"email": body.email.lower()})
    if not u or not verify_password(body.password, u["password_hash"]):
        limiter.fail(key)
        raise HTTPException(401, "Incorrect email or password")
    limiter.reset(key)
    return {"token": create_token(str(u["_id"])), "user": public_user(u)}


@router.get("/me")
async def me(user: dict = Depends(current_user)):
    return public_user(user)
