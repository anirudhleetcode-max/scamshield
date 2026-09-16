"""Robustness: bad input, abstention paths, missing / corrupt model, timeouts, security."""
import uuid

import pytest

from app.config import Settings, check_jwt_secret
from app.services import classifier
from app.services.analyzer import analyze


def _user(client):
    r = client.post("/api/auth/register", json={"name": "R", "email": f"r{uuid.uuid4().hex[:8]}@example.com",
                                                "password": "secret123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def user(client):
    return _user(client)


def test_malformed_json_and_wrong_types(client, user):
    h = user | {"Content-Type": "application/json"}
    r = client.post("/api/check/analyze", content=b"{not json", headers=h)
    assert r.status_code == 422 and r.json()["status"] == 422
    assert client.post("/api/check/analyze", json={"text": 123}, headers=user).status_code == 422
    assert client.post("/api/check/analyze", json={}, headers=user).status_code == 422
    assert client.post("/api/lookup", json={"value": "x" * 501}, headers=user).status_code == 422


def test_empty_and_whitespace_input(client, user):
    for text in ("", "   \n\t "):
        assert client.post("/api/check/analyze", json={"text": text}, headers=user).status_code == 422


def test_very_large_input_rejected(client, user):
    assert client.post("/api/check/analyze", json={"text": "a" * 2001}, headers=user).status_code == 422
    big = "word " * 20000
    assert client.post("/api/check/analyze", json={"text": big}, headers=user).status_code == 413


def test_max_length_input_is_handled(client, user):
    text = ("Dear customer your account is blocked, update KYC at http://sbi-kyc.xyz now. " * 30)[:2000]
    r = client.post("/api/check/analyze", json={"text": text}, headers=user)
    assert r.status_code == 200 and r.json()["verdict"] == "Scam"


@pytest.mark.parametrize("text,reason", [
    ("ok", "too_short"),
    ("hmm ??", "too_short"),
    ("आपका पार्सल कल आएगा, कृपया घर पर रहें", "non_latin_script"),
    ("https://www.example.org/some/long/path/page", "mostly_url"),
])
def test_abstention_reasons(client, user, text, reason):
    r = client.post("/api/check/analyze", json={"text": text}, headers=user).json()
    assert r["status"] == "insufficient_confidence"
    assert reason in [x["id"] for x in r["abstain_reasons"]]
    assert r["confidence_level"] == "low"
    assert r["verdict"] in ("Safe", "Suspicious", "Scam")  # legacy field still present


def test_risky_short_link_is_not_abstained(client, user):
    r = client.post("/api/check/analyze", json={"text": "http://sbi-kyc-update.xyz/login"}, headers=user).json()
    assert r["status"] == "decided" and r["verdict"] != "Safe"


def test_uncertain_model_band_abstains():
    model = classifier.get_model()
    band = model.ops["uncertain_band"]
    mid = (band["low"] + band["high"]) / 2

    class Fake:
        ops = model.ops
        version = model.version

        def predict(self, text):
            p = model.predict(text)
            p.scam_probability = mid
            return p

    r = analyze("Are we still meeting for lunch at the usual place tomorrow", None, {}, model=Fake())
    assert r["status"] == "insufficient_confidence"
    assert [x["id"] for x in r["abstain_reasons"]] == ["uncertain_model"]
    r = analyze("Please tell me the OTP you received right now", None, {}, model=Fake())
    assert r["status"] == "decided"  # rule evidence overrides the uncertain model


def test_saved_check_keeps_status(client, user):
    r = client.post("/api/checks", json={"text": "ok"}, headers=user).json()
    assert r["status"] == "insufficient_confidence"
    item = client.get("/api/checks", headers=user).json()["items"][0]
    assert item["status"] == "insufficient_confidence"


@pytest.fixture()
def restore_model():
    saved = (classifier._model, classifier._load_error)
    yield
    classifier.set_model(*saved)


def test_missing_model_degrades(client, user, tmp_path, restore_model):
    assert classifier.load_model(tmp_path / "nope.joblib") is None
    h = client.get("/api/health").json()
    assert h["status"] == "degraded" and not h["model_loaded"] and "not found" in h["model_error"]
    r = client.post("/api/check/analyze", json={"text": "hello there friend"}, headers=user)
    assert r.status_code == 503 and "not loaded" in r.json()["detail"]
    # rule-based features keep working
    assert client.post("/api/lookup", json={"value": "sbi-refund@ybl"}, headers=user).status_code == 200
    assert client.get("/api/model").json()["loaded"] is False


def test_corrupt_model_degrades(client, user, tmp_path, restore_model):
    art = tmp_path / "scamshield-9.9.9.joblib"
    art.write_bytes(b"this is not a pickle")
    (tmp_path / "scamshield-9.9.9.card.json").write_text(
        '{"model_version": "9.9.9", "operating_points": {"model_threshold": 0.5, "suspicious_score": 40, '
        '"scam_score": 70, "uncertain_band": {"low": 0.4, "high": 0.6}}}')
    assert classifier.load_model(art) is None
    assert classifier.model_status()["error"]
    assert client.post("/api/checks", json={"text": "hello there friend"}, headers=user).status_code == 503


def test_card_without_operating_points_is_rejected(tmp_path, restore_model):
    import shutil

    real = classifier.get_model()
    src, _ = classifier.artifact_paths(real.version, classifier.Path(classifier.get_settings().model_dir))
    art = tmp_path / src.name
    shutil.copy(src, art)
    (tmp_path / src.name.replace(".joblib", ".card.json")).write_text('{"model_version": "%s"}' % real.version)
    assert classifier.load_model(art) is None
    assert "operating points" in classifier.model_status()["error"]


def test_inference_timeout(client, user, monkeypatch):
    import time

    from app.config import get_settings
    from app.routers import check

    def slow(*a, **k):
        time.sleep(0.5)

    monkeypatch.setattr(check, "analyze", slow)
    monkeypatch.setattr(get_settings(), "inference_timeout_s", 0.05)
    r = client.post("/api/check/analyze", json={"text": "hello there friend"}, headers=user)
    assert r.status_code == 503 and "timed out" in r.json()["detail"]


def test_jwt_secret_policy():
    with pytest.raises(RuntimeError):
        check_jwt_secret(Settings(env="production", jwt_secret="change-me-in-production"))
    with pytest.raises(RuntimeError):
        check_jwt_secret(Settings(env="production", jwt_secret="short"))
    dev = check_jwt_secret(Settings(env="development", jwt_secret="change-me-in-production"))
    assert len(dev.jwt_secret) >= 32 and dev.jwt_secret != "change-me-in-production"
    good = "x" * 40
    assert check_jwt_secret(Settings(env="production", jwt_secret=good)).jwt_secret == good


def test_login_rate_limit(client):
    from app.auth import limiter

    email = f"rl{uuid.uuid4().hex[:6]}@example.com"
    client.post("/api/auth/register", json={"name": "RL", "email": email, "password": "secret123"})
    codes = [client.post("/api/auth/login", json={"email": email, "password": "wrongpass"}).status_code
             for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    ok = client.post("/api/auth/login", json={"email": email, "password": "secret123"})
    assert ok.status_code == 429  # still locked inside the window
    limiter.failures.clear()
    assert client.post("/api/auth/login", json={"email": email, "password": "secret123"}).status_code == 200


def test_password_rules(client):
    e = f"pw{uuid.uuid4().hex[:6]}@example.com"
    assert client.post("/api/auth/register", json={"name": "P", "email": e, "password": "short1"}).status_code == 422
    assert client.post("/api/auth/register", json={"name": "P", "email": e, "password": "é" * 40}).status_code == 422
    assert client.post("/api/auth/login", json={"email": e, "password": "x" * 129}).status_code == 422


def test_cors_only_configured_origins(client):
    ok = client.options("/api/health", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options("/api/health", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers
