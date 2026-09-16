"""Hand-written red-flag rules. Each rule returns the character spans that triggered it."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .identifiers import extract, norm_phone
from .upi import analyze_upi, analyze_upi_link
from .urls import analyze_url

NEGATION_RE = re.compile(r"\b(do not|don't|dont|never|not|mat|na|nahi|kabhi)\b[^.]{0,25}$", re.I)


@dataclass
class Rule:
    id: str
    label: str
    weight: float
    patterns: list[str] = field(default_factory=list)
    negatable: bool = False

    def __post_init__(self):
        self._res = [re.compile(p, re.I) for p in self.patterns]

    def find(self, text: str) -> list[tuple[int, int]]:
        spans = []
        for rx in self._res:
            for m in rx.finditer(text):
                if self.negatable and NEGATION_RE.search(text[max(0, m.start() - 30):m.start()]):
                    continue
                spans.append((m.start(), m.end()))
        return spans


TEXT_RULES = [
    Rule("urgency", "Creates urgency or threatens a block / disconnection", 0.12, [
        r"\b(urgent(ly)?|immediate(ly)?|turant|jaldi|right now|asap)\b",
        r"\bwithin \d+ ?(hours?|hrs?|minutes?|mins?)\b",
        r"\b(today|tonight|aaj( raat)?)\b[^.]{0,30}\b(block\w*|suspend\w*|disconnect\w*|band|kaat|cut|clos\w+|deactivat\w+|expire\w*)",
        r"\b(will be|has been|is)\s+(temporarily\s+)?(blocked|suspended|disconnected|deactivated|frozen|closed|locked)\b",
        r"\b(last|final) (chance|warning|reminder|notice)\b",
        r"\bexpires? (today|in \d+)",
    ]),
    Rule("asks_secret", "Asks you to share an OTP, PIN, CVV or password", 0.40, [
        r"\b(share|send|tell|forward|provide|give|reply with|bata\w*|bhej\w*)\b[^.]{0,40}\b(otp|one time password|pin|cvv|password|verification code|\d-digit code|code)\b",
        r"\b(otp|verification code)\b[^.]{0,30}\b(bata\w*|bhej\w*|forward)\b",
    ], negatable=True),
    Rule("upi_collect", "'Collect request' or 'enter PIN to receive money'", 0.35, [
        r"\b(enter|put|daal\w*|type)\b[^.]{0,20}\b(upi )?pin\b[^.]{0,30}\b(receive|get|claim|credit|milenge|aa jayenge|receive ho)",
        r"\b(accept|approve)\b[^.]{0,25}\b(collect )?request\b",
        r"\bcollect request\b",
        r"\bpin daal\w*",
        r"\bscan\b[^.]{0,30}\bqr\b[^.]{0,40}\b(receive|refund|get)\b",
    ]),
    Rule("impersonation", "Claims to be bank, customer-care or government staff", 0.15, [
        r"\b(calling|call|speaking|bol raha|bol rahi|this is|i am|main)\b[^.]{0,15}\b(from )?(your |the )?(bank|customer care|head office|kyc (officer|department)|rbi|npci|electricity (board|department|officer)|telecom department|trai)\b",
        r"\b(bank|kyc|electricity) (officer|executive|manager)\b",
    ]),
    Rule("app_install", "Asks you to install an app, APK or screen-sharing tool", 0.25, [
        r"\b(anydesk|teamviewer|quick ?support|rustdesk|airdroid)\b",
        r"\.apk\b",
        r"\b(install|download)\b[^.]{0,20}\b(app|application)\b[^.]{0,30}(http|www|\.[a-z]{2,6}/)",
    ]),
    Rule("threat", "Threatens arrest, legal action or leaking private content", 0.25, [
        r"\b(arrest\w*|warrant|fir|cbi|crime branch|cyber (cell|police)|digital arrest|money laundering)\b",
        r"\b(video|photos?)\b[^.]{0,40}\b(viral|leak\w*|upload\w*|contacts|family)\b",
        r"\b(photos?|videos?) will be (sent|shared|uploaded)",
    ]),
    Rule("money_lure", "Promises prizes, guaranteed returns or easy daily income", 0.15, [
        r"\b(you('ve| have)? won|winner|lucky draw|lottery|jeete|inam)\b",
        r"\b(guaranteed|pakka|100%)\b[^.]{0,20}\b(return|profit|returns)\b",
        r"\b(double (your|karo)|paisa double)\b",
        r"\bearn\b[^.]{0,30}\b(daily|per day|roz|weekly|per task)\b",
        r"\b(work from home|ghar baithe|part[- ]time job)\b",
        r"\b\d+% (daily|return)",
    ]),
    Rule("fee_first", "Asks for a fee before you receive money, a job or a prize", 0.15, [
        r"\b(processing|registration|joining|file|insurance|clearance|delivery|gst|training|withdrawal tax|security deposit|redelivery) (fee|charges?|tax)\b",
    ]),
]

FORMAT_RE = [
    re.compile(r"!{2,}"),
    re.compile(r"\b(dear (customer|user|consumer|valued customer|winner))\b", re.I),
    re.compile(r"\b(acount|verfy|immediatly|updte|suspand|recieve|detials|plz|kindly)\b", re.I),
]

BRAND_RE = re.compile(r"\b(sbi|hdfc|icici|axis|kotak|pnb|bank|yono|paytm|phonepe|google pay|amazon|flipkart|"
                      r"electricity|bescom|bijli|india post|courier|rbi|npci|police|cbi|kbc|jio|airtel)\b", re.I)
PAY_RE = re.compile(r"\b(pay|send|transfer|deposit|bhej\w*|fee|charges?|approve|accept)\b", re.I)
OFFICIAL_SENDER_RE = re.compile(r"^([A-Z]{2}-)?[A-Z0-9]{6}(-[SPTG])?$")


def check(text: str, sender: str | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (flags, rule_spans, identifier_analyses)."""
    flags: list[dict] = []
    spans: list[dict] = []

    for rule in TEXT_RULES:
        hits = rule.find(text)
        flags.append({"id": rule.id, "label": rule.label, "hit": bool(hits), "weight": rule.weight if hits else 0.0})
        spans += [{"start": s, "end": e, "text": text[s:e], "source": "rule", "rule": rule.id} for s, e in hits]

    # identifiers -> link / UPI rules
    idents = extract(text)
    link_hit, upi_hit = [], []
    for it in idents:
        if it["kind"] == "url":
            a = analyze_url(it["raw"])
        elif it["kind"] == "upi":
            a = analyze_upi(it["raw"])
        elif it["kind"] == "upi_link":
            a = analyze_upi_link(it["raw"])
        else:
            a = {"risk": "low", "flags": []}
        it["analysis"] = {"risk": a["risk"], "flags": a["flags"]}
        if it["kind"] in ("url", "upi_link") and a["risk"] in ("high", "medium"):
            link_hit.append(it)
        asks_payment = it["kind"] == "upi" and PAY_RE.search(text)
        if it["kind"] in ("upi", "upi_link") and (a["risk"] in ("high", "medium") or asks_payment):
            upi_hit.append(it)
        if a["risk"] in ("high", "medium") or asks_payment:
            spans.append({"start": it["start"], "end": it["end"], "text": it["raw"], "source": "rule",
                          "rule": "risky_link" if it["kind"] == "url" else "personal_upi"})

    link_w = 0.0
    if link_hit:
        link_w = 0.25 if any(i["analysis"]["risk"] == "high" for i in link_hit) else 0.15
    flags.append({"id": "risky_link", "label": "Shortened, look-alike or unsafe link", "hit": bool(link_hit),
                  "weight": link_w, "details": [f"{i['raw']} — " + "; ".join(f["label"] for f in i["analysis"]["flags"] if f["severity"] != "info")
                              for i in link_hit][:3]})
    upi_w = 0.0
    if upi_hit:
        upi_w = 0.2 if any(i["analysis"]["risk"] == "high" for i in upi_hit) else 0.1
    flags.append({"id": "personal_upi", "label": "Asks for payment to a personal or suspicious UPI ID",
                  "hit": bool(upi_hit), "weight": upi_w,
                  "details": [f"{i['raw']} — " + ("; ".join(f["label"] for f in i["analysis"]["flags"]) or "payment requested to this UPI ID")
                              for i in upi_hit][:3]})

    # sender
    sender_hit, sender_detail = False, None
    if sender and sender.strip():
        s = sender.strip()
        is_mobile = norm_phone(s) is not None
        brand = BRAND_RE.search(text)
        if is_mobile and brand:
            sender_hit = True
            sender_detail = f"Claims to be about '{brand.group()}' but comes from a personal mobile number"
        elif not is_mobile and not OFFICIAL_SENDER_RE.match(s.upper()):
            sender_hit = True
            sender_detail = "Sender ID does not match the registered header format (e.g. VM-HDFCBK)"
    flags.append({"id": "non_official_sender", "label": "Sent from a non-official number or ID",
                  "hit": sender_hit, "weight": 0.15 if sender_hit else 0.0,
                  "details": [sender_detail] if sender_detail else [],
                  "checked": bool(sender and sender.strip())})

    # format anomalies
    fmt_hits = [(m.start(), m.end()) for rx in FORMAT_RE for m in rx.finditer(text)]
    letters = [c for c in text if c.isalpha()]
    shouting = len(letters) > 30 and sum(c.isupper() for c in letters) / len(letters) > 0.6
    fmt = len(fmt_hits) >= 2 or shouting
    flags.append({"id": "format_anomaly", "label": "Odd grammar, spelling or formatting", "hit": fmt,
                  "weight": 0.08 if fmt else 0.0})
    if fmt:
        spans += [{"start": s, "end": e, "text": text[s:e], "source": "rule", "rule": "format_anomaly"} for s, e in fmt_hits]
    return flags, spans, idents
