"""Combines the ML model, the rule engine and community reports into one verdict.

Risk formula (noisy-OR: each source independently "explains" the risk)

    p = calibrated scam probability from the model            (0..1)
    R = min(0.6, sum of weights of the red-flag rules that fired)
    C = 0 if no identifier was reported, else min(0.65, 0.20 + 0.15 * n)
        where n = most distinct users that reported any phone / UPI ID / URL in the message
    risk  = 100 * (1 - (1 - 0.9 * p) * (1 - R) * (1 - C))

The Safe / Suspicious / Scam cut-offs are NOT constants in this file: they are operating
points chosen on the validation split by `python -m ml.train` and stored in the model
card (`operating_points.suspicious_score` / `scam_score`). One policy override: if a
SAFETY_FLOOR rule fires (asks for OTP/PIN, collect request, remote-access app) the verdict is
at least Suspicious.

Abstention ("insufficient confidence") - the verdict band is still computed, but
`status` becomes "insufficient_confidence" when the model should not decide:
    too_short        fewer than 3 words or 8 letters, and no rule / report evidence
    non_latin_script >30% of letters are non-Latin (training data is English + romanised Hindi),
                     unless rules or reports give strong evidence
    mostly_url       >70% of the text is a link and the link checks found nothing risky
    uncertain_model  model probability inside the validation-chosen uncertain band and
                     no rule or report evidence
"""
from __future__ import annotations

from ml.preprocess import quality_signals
from ml.templates import CATEGORY_LABELS, SAFE_CATEGORIES, SCAM_CATEGORIES

from . import rules
from .classifier import ScamModel, get_model

MIN_WORDS = 3
MIN_LETTERS = 8
MAX_NON_LATIN = 0.30
MAX_URL_RATIO = 0.70
STRONG_RULES = 0.25

REASON_TEXT = {
    "too_short": "The message is too short to judge from its wording.",
    "non_latin_script": "Most of the text is in a script the model was not trained on (it knows English and romanised Hindi).",
    "mostly_url": "The message is mostly a link. Check the link itself on the UPI & Links page.",
    "uncertain_model": "The model's probability is in its uncertain range and no rule or report backs either way.",
}

GENERIC_ADVICE = [
    "Never enter your UPI PIN to receive money. A PIN is only ever needed to send money.",
    "Banks, NPCI and government offices never ask for OTP, PIN, CVV or passwords by SMS, call or WhatsApp.",
    "If you lost money, call the national cyber fraud helpline 1930 immediately and file a complaint at cybercrime.gov.in.",
]
ABSTAIN_ADVICE = [
    "Treat it with caution: do not click links, share codes or pay until you have verified the sender through an official channel.",
    "Paste the full message (not just a fragment) for a better check.",
]
ADVICE = {
    "kyc_bank": ["Do not open the link. Check KYC status only inside your bank's official app or at a branch.",
                 "Call the number printed on the back of your debit card, not the number in the message."],
    "upi_collect": ["Decline the collect request in your UPI app. Receiving money never needs your PIN.",
                    "If a 'buyer' insists, stop the deal - genuine buyers simply send money."],
    "job_task": ["Real employers never ask for a registration or training fee.",
                 "'Prepaid tasks' that return a bonus are a trap - the next task always asks for more."],
    "lottery_prize": ["You cannot win a lottery you did not enter. Ignore and block the sender.",
                      "Never pay 'tax' or 'processing fee' to release a prize."],
    "loan_app": ["Use only lenders listed by RBI-regulated banks/NBFCs. Do not install APKs from links.",
                 "If an app threatens to share your photos, do not pay - report the app and call 1930."],
    "delivery_courier": ["Track parcels only on the courier's official website or the shopping app.",
                         "Couriers do not ask for small 'redelivery' payments through links."],
    "electricity_bill": ["Check your bill on your DISCOM's official app or website.",
                         "Electricity boards do not ask you to call a personal mobile number or install remote-access apps."],
    "otp_harvest": ["Do not forward any OTP or code - it lets someone else log in or pay as you.",
                    "If you already shared it, change your passwords and call your bank to block the account."],
    "investment_crypto": ["Guaranteed high returns are a warning sign. Check SEBI registration on sebi.gov.in.",
                          "Never pay a 'withdrawal tax' to release profits shown in an app."],
    "sextortion_threat": ["Do not pay - payment leads to more demands. Stop replying and keep screenshots.",
                          "Police and CBI never demand money over calls or 'digital arrest' video calls. Report at cybercrime.gov.in."],
    "legit_transactional": ["Looks like a routine alert. If you did not make this transaction, contact your bank using its official app."],
    "promotional": ["Looks like marketing. You can block promotional messages with DND (text START 0 to 1909)."],
    "personal": ["Looks like a normal personal message."],
}


def community_component(n: int) -> float:
    return 0.0 if n <= 0 else min(0.65, 0.20 + 0.15 * n)


def rules_component(flags: list[dict]) -> float:
    return min(0.6, sum(f["weight"] for f in flags))


def fuse(p: float, R: float, C: float) -> float:
    """Noisy-OR risk in [0, 1]."""
    return 1 - (1 - 0.9 * p) * (1 - R) * (1 - C)


# Safety floor: these red flags are never compatible with a legitimate message (a bank never asks
# for your OTP, receiving money never needs a PIN, nobody legitimate needs AnyDesk on your phone),
# so when one fires the verdict is at least "Suspicious" whatever the model says.
SAFETY_FLOOR_RULES = frozenset({"asks_secret", "upi_collect", "app_install"})


def verdict_for(score: float, ops: dict, hits: set[str] | frozenset[str] = frozenset()) -> str:
    if score >= ops["scam_score"]:
        return "Scam"
    if score >= ops["suspicious_score"] or hits & SAFETY_FLOOR_RULES:
        return "Suspicious"
    return "Safe"


def abstain_reasons(q: dict, p: float, R: float, C: float, risky_ident: bool, ops: dict) -> list[str]:
    evidence = R > 0 or C > 0 or risky_ident
    reasons = []
    if (q["n_words"] < MIN_WORDS or q["letters"] < MIN_LETTERS) and not evidence:
        reasons.append("too_short")
    if q["non_latin_ratio"] > MAX_NON_LATIN and not (R >= STRONG_RULES or C > 0 or risky_ident):
        reasons.append("non_latin_script")
    if q["url_ratio"] > MAX_URL_RATIO and not (risky_ident or C > 0):
        reasons.append("mostly_url")
    band = ops["uncertain_band"]
    if band["low"] <= p <= band["high"] and not evidence:
        reasons.append("uncertain_model")
    return reasons


def analyze(text: str, sender: str | None, report_counts: dict[tuple[str, str], int],
            model: ScamModel | None = None) -> dict:
    model = model or get_model()
    ops = model.ops
    pred = model.predict(text)
    flags, rule_spans, idents = rules.check(text, sender)
    q = quality_signals(text)

    p = pred.scam_probability
    R = rules_component(flags)
    n_max = 0
    report_spans = []
    for it in idents:
        n = report_counts.get((it["kind"], it["value"]), 0)
        it["reports"] = n
        if n:
            n_max = max(n_max, n)
            report_spans.append({"start": it["start"], "end": it["end"], "text": it["raw"], "source": "report",
                                 "rule": "community_report"})
    C = community_component(n_max)
    score = int(round(100 * fuse(p, R, C)))
    verdict = verdict_for(score, ops, {f["id"] for f in flags if f["hit"]})
    risky_ident = any(it["analysis"]["risk"] in ("high", "medium") for it in idents)
    reasons = abstain_reasons(q, p, R, C, risky_ident, ops)
    status = "insufficient_confidence" if reasons else "decided"

    flags.append({"id": "community_report", "label": "Contains a number, UPI ID or link reported by other users",
                  "hit": n_max > 0, "weight": round(C, 3),
                  "details": [f"{it['raw']}: reported by {it['reports']} user{'s' if it['reports'] != 1 else ''}"
                              for it in idents if it.get("reports")]})

    probs = pred.category_probs
    best_scam = max(SCAM_CATEGORIES, key=lambda c: probs.get(c, 0))
    best_safe = max(SAFE_CATEGORIES, key=lambda c: probs.get(c, 0))
    category = pred.category
    if verdict == "Scam" and category in SAFE_CATEGORIES:
        category = best_scam
    elif verdict == "Safe" and category in SCAM_CATEGORIES:
        category = best_safe

    band = ops["uncertain_band"]
    model_says_scam = p >= ops["model_threshold"]
    in_band = band["low"] <= p <= band["high"]
    if reasons or in_band:
        level = "low"
    elif model_says_scam == (verdict != "Safe"):
        level = "high"
    else:
        level = "medium"  # rules / reports overrode the model

    if status == "insufficient_confidence":
        advice = list(ABSTAIN_ADVICE) + GENERIC_ADVICE
    else:
        advice = list(ADVICE.get(category, []))
        if verdict != "Safe":
            advice += GENERIC_ADVICE
        elif any(f["hit"] for f in flags):
            advice.append("One or more red flags were found - read the checklist before acting.")

    spans = report_spans + rule_spans + (pred.spans if p >= 0.25 or verdict != "Safe" else [])
    top = sorted(probs.items(), key=lambda kv: -kv[1])[:3]
    return {
        "score": score,
        "verdict": verdict,
        "status": status,
        "abstain_reasons": [{"id": r, "text": REASON_TEXT[r]} for r in reasons],
        "scam_probability": round(p, 4),
        "confidence_level": level,
        "category": category,
        "category_label": CATEGORY_LABELS[category],
        "category_confidence": round(probs.get(category, 0.0), 3),
        "top_categories": [{"category": c, "label": CATEGORY_LABELS[c], "p": round(v, 3)} for c, v in top],
        "components": {"model": round(p, 3), "rules": round(R, 3), "community": round(C, 3)},
        "thresholds": {"suspicious": ops["suspicious_score"], "scam": ops["scam_score"],
                       "uncertain_low": band["low"], "uncertain_high": band["high"]},
        "input_quality": q,
        "spans": spans,
        "flags": flags,
        "identifiers": [{k: it[k] for k in ("kind", "value", "raw", "start", "end", "reports")} |
                        {"risk": it["analysis"]["risk"]} for it in idents],
        "advice": advice,
        "model_version": model.version,
    }
