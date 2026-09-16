"""UPI ID and upi:// deep-link analysis (pure rules, no ML)."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from .textutil import edit_distance

# Common PSP (payment service provider) handles. Not exhaustive - NPCI lists many more.
KNOWN_PSP = {
    "okaxis": "Google Pay (Axis)", "oksbi": "Google Pay (SBI)", "okhdfcbank": "Google Pay (HDFC)",
    "okicici": "Google Pay (ICICI)", "ybl": "PhonePe (Yes Bank)", "ibl": "PhonePe (ICICI)",
    "axl": "PhonePe (Axis)", "paytm": "Paytm", "ptyes": "Paytm (Yes Bank)", "ptaxis": "Paytm (Axis)",
    "pthdfc": "Paytm (HDFC)", "ptsbi": "Paytm (SBI)", "upi": "BHIM", "apl": "Amazon Pay",
    "yapl": "Amazon Pay (Yes Bank)", "rapl": "Amazon Pay (RBL)", "axisbank": "Axis Bank", "sbi": "SBI",
    "icici": "ICICI Bank", "hdfcbank": "HDFC Bank", "kotak": "Kotak", "pnb": "PNB", "barodampay": "Bank of Baroda",
    "idfcbank": "IDFC First", "indus": "IndusInd", "yesbank": "Yes Bank", "fbl": "Federal Bank", "jupiteraxis": "Jupiter",
    "freecharge": "Freecharge", "airtel": "Airtel Payments Bank", "jio": "Jio Payments Bank", "waicici": "WhatsApp Pay (ICICI)",
    "wahdfcbank": "WhatsApp Pay (HDFC)", "waaxis": "WhatsApp Pay (Axis)", "wasbi": "WhatsApp Pay (SBI)",
    "abfspay": "Aditya Birla", "cnrb": "Canara Bank", "unionbank": "Union Bank", "kbl": "Karnataka Bank",
}
BAIT_WORDS = ["support", "refund", "kyc", "helpdesk", "help.desk", "customercare", "customer.care", "care",
              "cashback", "reward", "claim", "prize", "lottery", "bonus", "gift", "verify", "helpline", "official"]
BRANDS = ["sbi", "hdfc", "icici", "axis", "kotak", "paytm", "phonepe", "gpay", "googlepay", "amazon", "flipkart",
          "npci", "rbi", "bescom", "electricity", "irctc", "yono"]
UPI_RE = re.compile(r"^([\w.\-]{2,64})@([a-zA-Z][a-zA-Z0-9]{1,31})$")


def analyze_upi(value: str) -> dict:
    v = value.strip()
    flags: list[dict] = []
    m = UPI_RE.match(v)
    if not m:
        return {"kind": "upi", "value": v.lower(), "valid_format": False, "risk": "high", "psp": None,
                "flags": [{"id": "bad_format", "label": "Not a valid UPI ID format (expected name@handle)", "severity": "high"}]}
    user, handle = m.group(1).lower(), m.group(2).lower()
    psp = KNOWN_PSP.get(handle)
    if not psp:
        close = [k for k in KNOWN_PSP if edit_distance(handle, k) <= (1 if len(k) <= 4 else 2)]
        if close:
            flags.append({"id": "lookalike_psp", "severity": "high",
                          "label": f"Handle '@{handle}' looks like '@{close[0]}' but is not a known PSP"})
        else:
            flags.append({"id": "unknown_psp", "severity": "medium",
                          "label": f"'@{handle}' is not in our list of common UPI handles"})
    bait = [w for w in BAIT_WORDS if w in user]
    brand = [b for b in BRANDS if b in user]
    if bait:
        flags.append({"id": "bait_word", "severity": "high",
                      "label": f"Name contains '{bait[0]}' - banks and apps never collect refunds or KYC via a UPI ID"})
    if brand and not re.fullmatch(r"\d{10}", user):
        flags.append({"id": "brand_in_name", "severity": "medium" if not bait else "high",
                      "label": f"Uses the brand name '{brand[0]}' in a personal-looking UPI ID"})
    if re.fullmatch(r"[6-9]\d{9}", user):
        flags.append({"id": "mobile_handle", "severity": "info",
                      "label": "Mobile-number based ID - this is an individual's account, not a company"})
    sev = {f["severity"] for f in flags}
    risk = "high" if "high" in sev else "medium" if "medium" in sev else "low"
    return {"kind": "upi", "value": f"{user}@{handle}", "valid_format": True, "psp": psp, "risk": risk, "flags": flags,
            "username": user, "handle": handle}


REFUND_WORDS = re.compile(r"refund|cashback|reward|prize|receive|claim|kyc|bonus|lottery|verify", re.I)


def analyze_upi_link(link: str) -> dict:
    parsed = urlparse(link.strip())
    q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    pa = q.get("pa", "")
    flags: list[dict] = []
    payee = analyze_upi(pa) if pa else None
    if not pa:
        flags.append({"id": "no_payee", "label": "Link has no payee address (pa)", "severity": "high"})
    elif payee:
        flags.extend(payee["flags"])
    am = q.get("am")
    note = " ".join(filter(None, [q.get("tn"), q.get("pn")]))
    flags.append({"id": "pays_out", "severity": "info" if not am else "medium",
                  "label": f"Opening this link sends money FROM you{' - amount ' + am + ' ' + q.get('cu', 'INR') if am else ''}. It can never credit you."})
    if REFUND_WORDS.search(note):
        flags.append({"id": "refund_note", "severity": "high",
                      "label": f"Payment note says '{note.strip()}' - a refund or prize never requires you to pay"})
    sev = {f["severity"] for f in flags}
    risk = "high" if "high" in sev else "medium" if "medium" in sev else "low"
    return {"kind": "upi_link", "value": link.strip(), "risk": risk, "flags": flags,
            "params": {"payee": pa, "name": q.get("pn"), "amount": am, "currency": q.get("cu"), "note": q.get("tn")},
            "payee": payee}
