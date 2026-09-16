"""ML + rule unit tests on fresh, hand-written messages (not produced by the generator)."""
import pytest

from app.services import identifiers
from app.services.analyzer import analyze, community_component, verdict_for
from app.services.classifier import get_model
from app.services.textprep import normalize
from app.services.upi import analyze_upi, analyze_upi_link
from app.services.urls import analyze_url

SCAMS = [
    ("Your HDFC netbanking will be suspended tonight, re-verify your PAN at http://hdfc-verify.top now", "kyc_bank"),
    ("Hi I am interested in buying your cycle. I have sent a request for Rs 3500, just approve it with your PIN to get money.", "upi_collect"),
    ("We are hiring! Earn Rs 3000 per day from home by reviewing products. Message HR on WhatsApp 9123456780", "job_task"),
    ("Dear consumer your bijli connection will be cut tonight at 9:30 as last month bill is not updated. Call 9012345678", "electricity_bill"),
    ("Sir, I am calling from bank, please tell me the OTP you received so I can stop the fraud transaction", "otp_harvest"),
]
SAFE = [
    "739201 is your OTP to login to Swiggy. Do not share this with anyone.",
    "Rs 1,250.00 debited from A/c XX4410 on 14-Sep-26 via UPI to ZOMATO. Not you? Call 18002586161 -Axis Bank",
    "Are you coming for the movie tonight? Show starts at 9.",
    "Your Amazon order of Bajaj mixer grinder has been delivered. Rate your experience in the app.",
]


@pytest.fixture(scope="module")
def model():
    return get_model()


def test_normalize_preserves_length():
    s = "Rs.4,999 to SBI İstanbul 9876543210"
    assert len(normalize(s)) == len(s)
    assert normalize("OTP 1234") == "otp 0000"


@pytest.mark.parametrize("text,category", SCAMS)
def test_fresh_scams_flagged(model, text, category):
    r = analyze(text, None, {})
    assert r["verdict"] in ("Suspicious", "Scam"), (r["score"], r["components"])
    top3 = [c["category"] for c in r["top_categories"]]
    assert category == r["category"] or category in top3


@pytest.mark.parametrize("text", SAFE)
def test_fresh_legit_messages_safe(model, text):
    r = analyze(text, None, {})
    assert r["verdict"] == "Safe", (r["score"], r["components"], r["category"])


def test_explanations_point_at_real_text(model):
    text = "URGENT: your SBI account is blocked. Update KYC at bit.ly/sbi-kyc9 immediately"
    r = analyze(text, None, {})
    assert r["spans"], "expected highlighted phrases"
    for s in r["spans"]:
        assert text[s["start"]:s["end"]] == s["text"]
    joined = " ".join(s["text"].lower() for s in r["spans"])
    assert "kyc" in joined or "blocked" in joined


def test_otp_warning_not_flagged_as_asking():
    r = analyze("OTP is 123456. Never share your OTP with anyone.", None, {})
    assert not next(f for f in r["flags"] if f["id"] == "asks_secret")["hit"]


def test_community_reports_raise_score(model):
    text = "Please call me back on 9876501234 regarding your order"
    base = analyze(text, None, {})
    reported = analyze(text, None, {("phone", "9876501234"): 3})
    assert reported["score"] > base["score"] + 20
    assert next(f for f in reported["flags"] if f["id"] == "community_report")["hit"]
    assert community_component(0) == 0 and community_component(10) == 0.65


def test_verdict_bands_come_from_model_card(model):
    ops = model.ops
    assert ops["chosen_on"] == "val"
    s, c = ops["suspicious_score"], ops["scam_score"]
    assert 0 < s < c <= 100
    assert [verdict_for(x, ops) for x in (s - 1, s, c - 1, c)] == ["Safe", "Suspicious", "Suspicious", "Scam"]


def test_safety_floor_rules_force_at_least_suspicious(model):
    ops = model.ops
    assert verdict_for(0, ops, {"asks_secret"}) == "Suspicious"
    assert verdict_for(0, ops, {"urgency"}) == "Safe"
    r = analyze("Please tell me the OTP you just received, I am calling from your bank", None, {})
    assert r["verdict"] != "Safe"


def test_non_official_sender(model):
    r = analyze("Your SBI account statement is ready.", "+91 98765 43210", {})
    assert next(f for f in r["flags"] if f["id"] == "non_official_sender")["hit"]
    r = analyze("Your SBI account statement is ready.", "VM-SBIINB", {})
    assert not next(f for f in r["flags"] if f["id"] == "non_official_sender")["hit"]


def test_identifier_extraction():
    found = identifiers.extract("Pay to refund.sbi@ybl or call +91 98765-43210, see bit.ly/x1 mail me a@gmail.com")
    kinds = {(f["kind"], f["value"]) for f in found}
    assert ("upi", "refund.sbi@ybl") in kinds
    assert ("phone", "9876543210") in kinds
    assert ("url", "bit.ly/x1") in kinds
    assert not any(f["kind"] == "upi" and "gmail" in f["value"] for f in found)


def test_upi_checks():
    assert analyze_upi("rahul.sharma@okaxis")["risk"] == "low"
    assert analyze_upi("sbi-refund@ybl")["risk"] == "high"
    look = analyze_upi("priya@okaxls")
    assert any(f["id"] == "lookalike_psp" for f in look["flags"])
    assert not analyze_upi("not a upi")["valid_format"]
    link = analyze_upi_link("upi://pay?pa=cashback.help@ybl&pn=Cashback&am=1999&tn=refund")
    assert link["risk"] == "high" and link["params"]["amount"] == "1999"


def test_url_checks():
    assert analyze_url("https://www.hdfcbank.com/personal")["risk"] == "low"
    assert analyze_url("http://hdfcbamk.com")["risk"] == "high"
    assert analyze_url("https://sbi-kyc-update.xyz/login")["risk"] == "high"
    assert analyze_url("http://192.168.10.5/pay")["risk"] == "high"
    assert any(f["id"] == "shortener" for f in analyze_url("bit.ly/abc")["flags"])
    assert any(f["id"] == "punycode" for f in analyze_url("https://xn--sbi-xyz.com")["flags"])
