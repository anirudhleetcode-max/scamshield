"""URL risk analysis (rules): shorteners, raw IPs, punycode, lookalike domains, risky TLDs."""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

from .textutil import edit_distance

SHORTENERS = {"bit.ly", "tinyurl.com", "cutt.ly", "is.gd", "rb.gy", "shorturl.at", "t.ly", "goo.gl", "ow.ly",
              "tiny.cc", "rebrand.ly", "bitly.com", "s.id", "v.gd", "shorte.st", "t.co", "lnkd.in", "surl.li"}
SUSPICIOUS_TLDS = {"xyz", "top", "click", "live", "info", "buzz", "icu", "shop", "online", "site", "vip", "cc",
                   "tk", "ml", "ga", "cf", "gq", "rest", "monster", "cyou", "sbs", "cfd", "quest", "support", "work"}
TWO_LEVEL_SUFFIXES = {"co.in", "gov.in", "org.in", "net.in", "ac.in", "nic.in", "res.in", "in.net", "co.uk", "com.au"}
# official registrable domains -> brand
OFFICIAL = {
    "onlinesbi.sbi": "SBI", "sbi.co.in": "SBI", "bank.sbi": "SBI", "hdfcbank.com": "HDFC Bank", "icicibank.com": "ICICI Bank",
    "axisbank.com": "Axis Bank", "kotak.com": "Kotak", "pnbindia.in": "PNB", "bankofbaroda.in": "Bank of Baroda",
    "canarabank.com": "Canara Bank", "paytm.com": "Paytm", "phonepe.com": "PhonePe", "amazon.in": "Amazon",
    "amazon.com": "Amazon", "flipkart.com": "Flipkart", "myntra.com": "Myntra", "indiapost.gov.in": "India Post",
    "npci.org.in": "NPCI", "rbi.org.in": "RBI", "uidai.gov.in": "UIDAI", "incometax.gov.in": "Income Tax",
    "cybercrime.gov.in": "National Cyber Crime Portal", "irctc.co.in": "IRCTC", "bescom.co.in": "BESCOM",
    "karnataka.gov.in": "Govt of Karnataka", "delhivery.com": "Delhivery", "bluedart.com": "Blue Dart",
    "nykaa.com": "Nykaa", "swiggy.com": "Swiggy", "zomato.com": "Zomato", "google.com": "Google",
    "marutisuzuki.com": "Maruti Suzuki", "dtdc.in": "DTDC", "jio.com": "Jio", "airtel.in": "Airtel",
}
BRAND_TOKENS = {"sbi", "onlinesbi", "yono", "hdfc", "hdfcbank", "icici", "icicibank", "axis", "axisbank", "kotak",
                "paytm", "phonepe", "amazon", "flipkart", "indiapost", "npci", "rbi", "uidai", "aadhaar", "incometax",
                "irctc", "bescom", "delhivery", "bluedart", "netbanking", "myntra"}
BAIT_TOKENS = {"kyc", "verify", "update", "secure", "login", "refund", "reward", "claim", "support", "helpdesk",
               "bonus", "gift", "free", "account", "block", "unlock", "pan", "aadhar"}


def _registrable(host: str) -> tuple[str, str]:
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in TWO_LEVEL_SUFFIXES:
        return ".".join(parts[-3:]), ".".join(parts[-2:])
    return ".".join(parts[-2:]), parts[-1]


def analyze_url(value: str) -> dict:
    raw = value.strip()
    url = raw if re.match(r"^[a-z][a-z0-9+.\-]*://", raw, re.I) else "http://" + raw
    flags: list[dict] = []
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower().rstrip(".")
    except ValueError:
        host = ""
    if not host:
        return {"kind": "url", "value": raw, "host": None, "risk": "high",
                "flags": [{"id": "bad_url", "label": "Could not parse this as a web address", "severity": "high"}]}

    scheme_given = re.match(r"^https?://", raw, re.I)
    if scheme_given and parts.scheme.lower() == "http":
        flags.append({"id": "no_https", "severity": "medium", "label": "Uses plain http:// - no encryption"})
    if "@" in (parts.netloc or ""):
        flags.append({"id": "userinfo", "severity": "high", "label": "Contains '@' before the host - the real site is after it"})
    try:
        ipaddress.ip_address(host)
        flags.append({"id": "ip_host", "severity": "high", "label": "Points to a raw IP address instead of a domain"})
        is_ip = True
    except ValueError:
        is_ip = False

    reg, tld = _registrable(host) if not is_ip else (host, "")
    brand = OFFICIAL.get(reg)
    if host in SHORTENERS or reg in SHORTENERS:
        flags.append({"id": "shortener", "severity": "medium", "label": f"Link shortener ({reg}) hides the real destination"})
    if "xn--" in host:
        flags.append({"id": "punycode", "severity": "high", "label": "Punycode domain - may use look-alike Unicode letters"})
    if not is_ip and tld in SUSPICIOUS_TLDS | {"in.net"}:
        flags.append({"id": "suspicious_tld", "severity": "medium", "label": f"'.{tld}' domains are cheap and common in phishing"})
    if not is_ip and not brand:
        label = reg.split(".")[0]
        tokens = set(re.split(r"[\-.]", host))
        lookalike = next((o for o in OFFICIAL if edit_distance(label, o.split(".")[0]) in (1, 2)
                          and len(label) >= 4), None)
        brand_hit = sorted(t for t in BRAND_TOKENS if any(
            tok.startswith(t) or tok.endswith(t) or (len(t) >= 5 and t in tok) for tok in tokens))
        if lookalike:
            flags.append({"id": "lookalike", "severity": "high",
                          "label": f"'{reg}' is one or two letters away from the official '{lookalike}'"})
        elif brand_hit:
            flags.append({"id": "brand_in_domain", "severity": "high",
                          "label": f"Uses the name '{brand_hit[0]}' but is not an official {brand_hit[0].upper()} domain"})
        if tokens & BAIT_TOKENS:
            flags.append({"id": "bait_words", "severity": "medium",
                          "label": f"Domain contains '{sorted(tokens & BAIT_TOKENS)[0]}' - typical of phishing pages"})
    if host.count(".") >= 4:
        flags.append({"id": "deep_subdomain", "severity": "medium", "label": "Unusually many subdomains"})
    if len(raw) > 120:
        flags.append({"id": "long_url", "severity": "low", "label": "Very long URL"})
    if re.search(r"\.apk(\?|$)", parts.path or "", re.I):
        flags.append({"id": "apk", "severity": "high", "label": "Downloads an Android app (.apk) outside the Play Store"})

    sev = {f["severity"] for f in flags}
    risk = "high" if "high" in sev else "medium" if "medium" in sev else "low"
    return {"kind": "url", "value": raw, "host": host, "registrable_domain": reg, "official_brand": brand,
            "risk": risk if not (brand and risk != "high") else "low", "flags": flags}
