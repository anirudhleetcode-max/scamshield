"""Seed a demo account with ~30 days of realistic activity.

    python -m scripts.seed

Creates demo@scamshield.app / demo1234 (re-running resets its data), a few "community"
reporter accounts, fraud reports for a set of numbers / UPI IDs / links, and ~75 checks
analysed by the real model and back-dated across the last 30 days.
"""
from __future__ import annotations

import os
import random
import struct
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo import MongoClient

from app.config import get_settings
from app.security import hash_password
from app.services import identifiers
from app.services.analyzer import analyze
from ml.generate_dataset import fill
from ml.templates import SAFE_CATEGORIES, SCAM_CATEGORIES, TEMPLATES

DEMO_EMAIL = "demo@scamshield.app"
DEMO_PASSWORD = "demo1234"
REPORTED = [  # (kind, value, category, n_reporters)
    ("phone", "9123456780", "kyc_bank", 7),
    ("upi", "sbi.refund24@ybl", "upi_collect", 6),
    ("url", "hdfc-kyc-update.xyz/login", "kyc_bank", 5),
    ("phone", "8800112233", "electricity_bill", 5),
    ("upi", "helpdesk.paytm@axl", "upi_collect", 4),
    ("url", "bit.ly/3kycupd", "kyc_bank", 3),
    ("phone", "7011223344", "job_task", 3),
    ("url", "indiapost-track.top", "delivery_courier", 2),
    ("upi", "cashback786@okicici", "lottery_prize", 2),
    ("phone", "9988776655", "sextortion_threat", 1),
]
DEMO_MESSAGES = [  # hand-written ones that use reported identifiers, so the demo shows community flags
    ("Dear customer your SBI YONO is blocked. Call KYC desk 9123456780 now to reactivate.", "9123456780"),
    ("Refund of Rs 2,499 approved. Accept collect request from sbi.refund24@ybl to receive.", None),
    ("Bijli bill update nahi hua, aaj raat 9:30 connection kat jayega. Contact 8800112233", "8800112233"),
    ("HDFC: your netbanking is on hold. Verify at https://hdfc-kyc-update.xyz/login", "VK-HDFCKY"),
]
BORDERLINE = [  # ambiguous messages that usually land in the Suspicious band
    ("Hi, this is Rohit from the courier office. Your parcel is here, call me on 7011223344", None),
    ("Your electricity bill is due tomorrow. Pay quickly using bit.ly/pay-bill24", None),
    ("Hello dear, I got your number from a friend. Are you interested in a part time opportunity?", "+91 9812012345"),
    ("Sir please send the OTP, I am the delivery boy standing at your gate", None),
    ("Congratulations! You are selected for a free gift. Visit our store to collect.", None),
    ("Dear customer, kindly update your details at the nearest branch to avoid inconvenience.", "+91 9876512345"),
    ("Your Amazon refund is pending. Reply with your UPI ID to receive it.", None),
    ("Bhai urgent hai, 2000 bhej de na abhi, kal wapas kar dunga", "+91 9123412345"),
]


def oid_at(dt: datetime) -> ObjectId:
    """ObjectId whose timestamp matches `dt`, so _id order == created_at order."""
    return ObjectId(struct.pack(">I", int(dt.timestamp())) + os.urandom(8))


def main() -> None:
    s = get_settings()
    db = MongoClient(s.mongo_uri, tz_aware=True)[s.mongo_db]
    rnd = random.Random(7)
    now = datetime.now(timezone.utc)

    demo = db.users.find_one({"email": DEMO_EMAIL})
    if demo:
        db.checks.delete_many({"user_id": demo["_id"]})
        db.reports.delete_many({"user_id": demo["_id"]})
        demo_id = demo["_id"]
    else:
        demo_id = db.users.insert_one({"name": "Ananya Rao", "email": DEMO_EMAIL,
                                       "password_hash": hash_password(DEMO_PASSWORD), "created_at": now - timedelta(days=35)}).inserted_id

    # community reporters
    reporter_ids = []
    for i in range(1, 8):
        email = f"reporter{i}@scamshield.app"
        u = db.users.find_one({"email": email})
        if not u:
            uid = db.users.insert_one({"name": f"Reporter {i}", "email": email,
                                       "password_hash": hash_password(os.urandom(12).hex()),
                                       "created_at": now - timedelta(days=40)}).inserted_id
        else:
            uid = u["_id"]
            db.reports.delete_many({"user_id": uid})
        reporter_ids.append(uid)
    for kind, value, cat, n in REPORTED:
        for uid in reporter_ids[:n]:
            when = now - timedelta(days=rnd.uniform(0, 28))
            db.reports.insert_one({"_id": oid_at(when), "user_id": uid, "kind": kind, "value": value,
                                   "category": cat, "note": None, "created_at": when})
    for kind, value, cat, _ in REPORTED[:3]:  # the demo user has reported a few too
        when = now - timedelta(days=rnd.uniform(1, 20))
        db.reports.insert_one({"_id": oid_at(when), "user_id": demo_id, "kind": kind, "value": value,
                               "category": cat, "note": "Got this on WhatsApp", "created_at": when})

    counts: dict[tuple[str, str], int] = {}
    for r in db.reports.aggregate([{"$group": {"_id": {"k": "$kind", "v": "$value"}, "n": {"$sum": 1}}}]):
        counts[(r["_id"]["k"], r["_id"]["v"])] = r["n"]

    samples: list[tuple[str, str | None]] = list(DEMO_MESSAGES) + BORDERLINE
    for _ in range(66):
        cat = rnd.choice(SAFE_CATEGORIES) if rnd.random() < 0.45 else rnd.choice(SCAM_CATEGORIES)
        text = fill(rnd, rnd.choice(TEMPLATES[cat]))
        sender = None
        if rnd.random() < 0.6:
            sender = (rnd.choice(["VM-", "AD-", "JD-", "BZ-"]) + rnd.choice(["HDFCBK", "SBIINB", "AMAZON", "SWIGGY", "ICICIT"])
                      if cat in SAFE_CATEGORIES else "+91 " + rnd.choice("6789") + "".join(rnd.choices("0123456789", k=9)))
        samples.append((text, sender))

    docs = []
    for i, (text, sender) in enumerate(samples):
        days_ago = rnd.betavariate(1.0, 1.6) * 29.5 if i >= len(DEMO_MESSAGES) else rnd.uniform(0, 3)
        when = now - timedelta(days=days_ago, minutes=rnd.randint(0, 600))
        pairs = {(x["kind"], x["value"]) for x in identifiers.extract(text)}
        result = analyze(text, sender, {p: counts[p] for p in pairs if p in counts})
        docs.append({
            "_id": oid_at(when), "user_id": demo_id, "text": text, "sender": sender,
            "score": result["score"], "verdict": result["verdict"], "category": result["category"],
            "flags_hit": [f["id"] for f in result["flags"] if f["hit"]],
            "identifiers": [{"kind": x["kind"], "value": x["value"]} for x in result["identifiers"]],
            "result": result, "created_at": when,
        })
    db.checks.insert_many(docs)
    verdicts = {v: sum(d["verdict"] == v for d in docs) for v in ("Safe", "Suspicious", "Scam")}
    print(f"seeded {len(docs)} checks {verdicts} and {db.reports.count_documents({})} reports")
    print(f"login: {DEMO_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
