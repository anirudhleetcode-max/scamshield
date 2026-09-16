"""Combines the ML model, the rule engine and community reports into one verdict.

Risk formula (noisy-OR: each source independently "explains" the risk)

    p = calibrated scam probability from the model            (0..1)
    R = min(0.6, sum of weights of the red-flag rules that fired)
    C = 0 if no identifier was reported, else min(0.65, 0.20 + 0.15 * n)
        where n = most distinct users that reported any phone / UPI ID / URL in the message
    risk  = 100 * (1 - (1 - 0.9 * p) * (1 - R) * (1 - C))

    verdict: risk < 35 -> Safe, 35..69 -> Suspicious, >= 70 -> Scam
"""
from __future__ import annotations

from ml.templates import CATEGORY_LABELS, SAFE_CATEGORIES, SCAM_CATEGORIES

from . import rules
from .classifier import get_model

SAFE_MAX = 35
SUSPICIOUS_MAX = 70

GENERIC_ADVICE = [
    "Never enter your UPI PIN to receive money. A PIN is only ever needed to send money.",
    "Banks, NPCI and government offices never ask for OTP, PIN, CVV or passwords by SMS, call or WhatsApp.",
    "If you lost money, call the national cyber fraud helpline 1930 immediately and file a complaint at cybercrime.gov.in.",
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


def verdict_for(score: int) -> str:
    return "Safe" if score < SAFE_MAX else "Suspicious" if score < SUSPICIOUS_MAX else "Scam"


def analyze(text: str, sender: str | None, report_counts: dict[tuple[str, str], int]) -> dict:
    model = get_model()
    pred = model.predict(text)
    flags, rule_spans, idents = rules.check(text, sender)

    p = pred.scam_probability
    R = min(0.6, sum(f["weight"] for f in flags))
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
    risk = 1 - (1 - 0.9 * p) * (1 - R) * (1 - C)
    score = int(round(100 * risk))
    verdict = verdict_for(score)

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
        "category": category,
        "category_label": CATEGORY_LABELS[category],
        "category_confidence": round(probs.get(category, 0.0), 3),
        "top_categories": [{"category": c, "label": CATEGORY_LABELS[c], "p": round(v, 3)} for c, v in top],
        "components": {"model": round(p, 3), "rules": round(R, 3), "community": round(C, 3)},
        "spans": spans,
        "flags": flags,
        "identifiers": [{k: it[k] for k in ("kind", "value", "raw", "start", "end", "reports")} |
                        {"risk": it["analysis"]["risk"]} for it in idents],
        "advice": advice,
        "model_version": model.version,
    }
