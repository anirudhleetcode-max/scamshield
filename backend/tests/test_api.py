import uuid

import pytest

SCAM = "Dear SBI customer, your account will be blocked today. Update KYC immediately: http://sbi-kyc.xyz/login"
SAFE = "482913 is your OTP for txn of Rs 2,000 at Amazon on HDFC card XX1234. Do not share it with anyone."


def _new_user(client):
    r = client.post("/api/auth/register", json={"name": "U", "email": f"u{uuid.uuid4().hex[:8]}@example.com",
                                                "password": "secret123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def user(client):
    return _new_user(client)


def test_requires_auth(client):
    assert client.post("/api/check/analyze", json={"text": "hi"}).status_code == 401


def test_analyze_live_does_not_save(client, user):
    r = client.post("/api/check/analyze", json={"text": SCAM}, headers=user)
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "Scam" and body["category"] == "kyc_bank"
    assert body["spans"] and body["advice"]
    assert client.get("/api/checks", headers=user).json()["total"] == 0


def test_validation_errors(client, user):
    r = client.post("/api/check/analyze", json={"text": "   "}, headers=user)
    assert r.status_code == 422 and r.json()["status"] == 422
    assert client.post("/api/check/analyze", json={"text": "x" * 2001}, headers=user).status_code == 422
    big = client.post("/api/check/analyze", content=b"{" + b" " * 70000 + b"}", headers=user | {"Content-Type": "application/json"})
    assert big.status_code == 413


def test_save_history_filters_and_pagination(client, user):
    ids = []
    for text in [SCAM, SAFE, SAFE + " ", SCAM + "!"]:
        r = client.post("/api/checks", json={"text": text, "sender": "9876543210"}, headers=user)
        assert r.status_code == 201
        ids.append(r.json()["id"])
    page = client.get("/api/checks?limit=3", headers=user).json()
    assert page["total"] == 4 and len(page["items"]) == 3 and page["next_cursor"]
    assert page["items"][0]["id"] == ids[-1]  # newest first
    rest = client.get(f"/api/checks?limit=3&cursor={page['next_cursor']}", headers=user).json()
    assert len(rest["items"]) == 1 and rest["next_cursor"] is None
    scams = client.get("/api/checks?verdict=Scam", headers=user).json()
    assert scams["total"] == 2 and all(i["verdict"] == "Scam" for i in scams["items"])
    assert client.get("/api/checks?q=OTP", headers=user).json()["total"] == 2
    assert client.get("/api/checks?category=nope", headers=user).status_code == 422

    detail = client.get(f"/api/checks/{ids[0]}", headers=user).json()
    assert detail["result"]["verdict"] == "Scam"
    other = _new_user(client)
    assert client.get(f"/api/checks/{ids[0]}", headers=other).status_code == 404
    assert client.delete(f"/api/checks/{ids[0]}", headers=other).status_code == 404
    assert client.delete(f"/api/checks/{ids[0]}", headers=user).status_code == 204
    assert client.get("/api/checks", headers=user).json()["total"] == 3


def test_reports_unique_and_counted(client, user):
    phone = "9811122233"
    r = client.post("/api/reports", json={"kind": "phone", "value": "+91 98111 22233", "category": "kyc_bank"}, headers=user)
    assert r.status_code == 201 and r.json()["value"] == phone
    dup = client.post("/api/reports", json={"kind": "phone", "value": phone, "category": "otp_harvest"}, headers=user)
    assert dup.status_code == 409
    other = _new_user(client)
    assert client.post("/api/reports", json={"kind": "phone", "value": "09811122233"}, headers=other).status_code == 201
    assert client.post("/api/reports", json={"kind": "phone", "value": "12345"}, headers=other).status_code == 422

    look = client.post("/api/lookup", json={"value": "98111 22233"}, headers=user).json()
    assert look["kind"] == "phone" and look["reports"]["count"] == 2 and look["risk"] == "high"

    msg = f"Hello, call me on {phone} regarding your parcel"
    res = client.post("/api/check/analyze", json={"text": msg}, headers=user).json()
    flag = next(f for f in res["flags"] if f["id"] == "community_report")
    assert flag["hit"] and res["components"]["community"] > 0
    assert any(s["source"] == "report" for s in res["spans"])

    mine = client.get("/api/reports", headers=user).json()["items"]
    assert mine[0]["total_reports"] == 2
    top = client.get("/api/reports/top", headers=user).json()["items"]
    assert top[0]["value"] == phone and top[0]["reports"] == 2
    assert client.delete(f"/api/reports/{mine[0]['id']}", headers=other).status_code == 404
    assert client.delete(f"/api/reports/{mine[0]['id']}", headers=user).status_code == 204


def test_lookup_kinds(client, user):
    upi = client.post("/api/lookup", json={"value": "sbi-refund@ybl"}, headers=user).json()
    assert upi["kind"] == "upi" and upi["risk"] == "high"
    url = client.post("/api/lookup", json={"value": "https://onlinesbi.sbi"}, headers=user).json()
    assert url["kind"] == "url" and url["risk"] == "low" and url["official_brand"] == "SBI"
    link = client.post("/api/lookup", json={"value": "upi://pay?pa=kyc.help@ybl&am=10&tn=KYC"}, headers=user).json()
    assert link["kind"] == "upi_link" and link["report_target"] == {"kind": "upi", "value": "kyc.help@ybl"}
    assert client.post("/api/lookup", json={"value": "12"}, headers=user).status_code == 422


def test_insights(client, user):
    client.post("/api/checks", json={"text": SCAM}, headers=user)
    client.post("/api/checks", json={"text": SAFE}, headers=user)
    ins = client.get("/api/insights", headers=user).json()
    assert len(ins["per_day"]) == 30
    assert sum(d["Safe"] + d["Suspicious"] + d["Scam"] for d in ins["per_day"]) == 2
    assert ins["totals"]["checks"] == 2 and ins["totals"]["flagged_share"] == 0.5
    assert {c["category"] for c in ins["categories"]} == {"kyc_bank", "legit_transactional"}
    assert "top_reported" in ins


def test_model_info(client):
    m = client.get("/api/model").json()
    assert m["available"] and 0 < m["heldout_binary"]["f1"] <= 1
