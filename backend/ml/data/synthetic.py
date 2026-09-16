"""SYNTHETIC Indian scam / legitimate message generator.

Templates from ml/templates.py are filled with slot values (banks, amounts, names,
UPI handles, URLs ...) and random typo / casing noise. Every row is synthetic and is
labelled as such in the manifest, the model card and the UI.
"""
from __future__ import annotations

import random
import re
import string

from ..templates import SCAM_CATEGORIES, TEMPLATES
from .schema import Record, validate

NAME = "synthetic_in"
GENERATOR_VERSION = "2.0"
SEED = 42

# samples per template (train pool / test pool)
PER_TEMPLATE = {"legit_transactional": 70, "promotional": 45, "personal": 40}
DEFAULT_PER_TEMPLATE = 45

BANKS = [("State Bank of India", "SBI"), ("HDFC Bank", "HDFC"), ("ICICI Bank", "ICICI"), ("Axis Bank", "AXIS"),
         ("Kotak Mahindra Bank", "KOTAK"), ("Punjab National Bank", "PNB"), ("Bank of Baroda", "BOB"),
         ("Canara Bank", "CANARA"), ("Union Bank of India", "UBI"), ("IndusInd Bank", "INDUSIND"),
         ("Yes Bank", "YES BANK"), ("IDFC First Bank", "IDFC")]
NAMES = ["Rahul", "Priya", "Amit", "Sneha", "Vikram", "Anjali", "Arjun", "Kavya", "Rohan", "Pooja", "Suresh",
         "Meena", "Imran", "Fatima", "Harpreet", "Deepak", "Lakshmi", "Karthik", "Neha", "Sanjay", "Ayesha", "Joseph"]
COMPANIES = ["Amazon", "Flipkart", "Myntra", "Swiggy", "Zomato", "Meesho", "Ajio", "Nykaa", "BigBasket", "Paytm"]
COURIERS = ["India Post", "Blue Dart", "DTDC", "Delhivery", "Ecom Express", "FedEx", "Shadowfax", "Xpressbees"]
DISCOMS = ["BESCOM", "MSEDCL", "TPDDL", "BSES Rajdhani", "TNEB", "UPPCL", "WBSEDCL", "Adani Electricity", "KSEB"]
LOAN_APPS = ["RupeeMitra", "PaisaTurant", "EasyLoan24", "CashKaro Loan", "InstaRupee", "QuickPaisa", "LoanDost"]
CRYPTO_APPS = ["WealthX Pro", "TradeGuru VIP", "CoinVault India", "BullRun AI", "USDT Mining Club", "ProfitMax"]
ITEMS = ["boAt earphones", "a Redmi phone", "running shoes", "a kurta set", "a pressure cooker", "a laptop bag"]
PSPS = ["okaxis", "oksbi", "okhdfcbank", "okicici", "ybl", "ibl", "axl", "paytm", "upi", "apl"]
SCAM_UPI_WORDS = ["refund", "support", "kyc", "helpdesk", "customercare", "cashback", "reward", "sbi.refund",
                  "hdfc.care", "claim", "gift", "help.desk", "bonus"]
BRAND_WORDS = ["sbi", "hdfc", "icici", "axis", "kotak", "indiapost", "bescom", "paytm", "amazon", "flipkart",
               "yono", "netbanking", "kyc", "rbi", "npci", "phonepe"]
SCAM_WORDS = ["update", "kyc", "verify", "secure", "login", "refund", "reward", "claim", "track", "support", "help"]
SUS_TLDS = ["xyz", "top", "click", "live", "info", "buzz", "icu", "shop", "online", "site", "in.net", "co", "cc", "vip"]
SHORTENERS = ["bit.ly", "tinyurl.com", "cutt.ly", "is.gd", "rb.gy", "shorturl.at", "t.ly"]
LEGIT_URLS = ["https://www.amazon.in/orders", "https://www.flipkart.com", "https://www.myntra.com/sale",
              "https://www.onlinesbi.sbi", "https://www.hdfcbank.com", "https://www.icicibank.com/cards",
              "https://bescom.karnataka.gov.in", "https://www.indiapost.gov.in", "https://www.nykaa.com",
              "https://www.delhivery.com/track", "https://www.marutisuzuki.com/service", "https://www.bluedart.com"]


def _rand_digits(r: random.Random, n: int) -> str:
    return "".join(r.choice(string.digits) for _ in range(n))


def _amount(r: random.Random, lo: int, hi: int) -> str:
    v = r.randint(lo, hi)
    if r.random() < 0.4:
        v = round(v, -2) or v
    fmt = r.choice(["Rs.{:,}", "Rs {}", "INR {:,}", "₹{:,}", "Rs.{}.00", "rs {}", "₹ {}"])
    return fmt.format(v)


def _phone(r: random.Random) -> str:
    n = r.choice("6789") + _rand_digits(r, 9)
    return r.choice([n, "+91" + n, "+91 " + n[:5] + " " + n[5:], "0" + n, "+91-" + n])


def _scam_url(r: random.Random) -> str:
    k = r.random()
    if k < 0.25:
        return f"{r.choice(['https://', 'http://', ''])}{r.choice(SHORTENERS)}/{''.join(r.choices(string.ascii_letters + string.digits, k=r.randint(5, 7)))}"
    if k < 0.35:
        return f"http://{r.randint(11, 223)}.{r.randint(0, 255)}.{r.randint(0, 255)}.{r.randint(1, 254)}/{r.choice(SCAM_WORDS)}"
    sep = r.choice(["-", "", "."])
    host = f"{r.choice(BRAND_WORDS)}{sep}{r.choice(SCAM_WORDS)}"
    if r.random() < 0.3:
        host += sep + r.choice(["online", "india", "in", "portal", "24"])
    return f"{r.choice(['https://', 'http://', 'http://www.', ''])}{host}.{r.choice(SUS_TLDS)}{r.choice(['', '/', '/login', '/kyc', '/update.php', '/?id=' + _rand_digits(r, 5)])}"


def _scam_upi(r: random.Random) -> str:
    u = r.choice(SCAM_UPI_WORDS)
    if r.random() < 0.5:
        u += _rand_digits(r, r.randint(2, 4))
    if r.random() < 0.3:  # ordinary-looking personal handle used as a mule account
        u = r.choice(NAMES).lower() + r.choice(["", ".", "_"]) + _rand_digits(r, r.randint(2, 4))
    return f"{u}@{r.choice(PSPS)}"


def build_slots(r: random.Random) -> dict:
    bank, bank_short = r.choice(BANKS)
    return {
        "bank": lambda: bank,
        "bank_short": lambda: bank_short if r.random() < 0.8 else bank,
        "name": lambda: r.choice(NAMES),
        "company": lambda: r.choice(COMPANIES),
        "courier": lambda: r.choice(COURIERS),
        "discom": lambda: r.choice(DISCOMS),
        "loan_app": lambda: r.choice(LOAN_APPS),
        "crypto_app": lambda: r.choice(CRYPTO_APPS),
        "item": lambda: r.choice(ITEMS),
        "amt": lambda: _amount(r, 99, 99999),
        "amt2": lambda: _amount(r, 500, 250000),
        "small_amt": lambda: _amount(r, 49, 2999),
        "big_amt": lambda: _amount(r, 5000, 2500000),
        "acct": lambda: r.choice(["XX", "xx", "*", "XXXX", "A/c XX", "**"]) + _rand_digits(r, 4),
        "date": lambda: r.choice([f"{r.randint(1, 28):02d}-{r.choice(['Jan', 'Mar', 'Jun', 'Aug', 'Sep', 'Oct', 'Dec'])}-26",
                                  f"{r.randint(1, 28):02d}/{r.randint(1, 12):02d}/2026", f"{r.randint(1, 28)} Sep"]),
        "time": lambda: f"{r.randint(1, 12)}:{r.choice(['00', '15', '30', '45'])} {r.choice(['AM', 'PM', 'pm'])}",
        "otp": lambda: _rand_digits(r, r.choice([4, 6, 6])),
        "ref": lambda: _rand_digits(r, 12),
        "order": lambda: "OD" + _rand_digits(r, 10) if r.random() < 0.5 else "40" + _rand_digits(r, 5) + "-" + _rand_digits(r, 7),
        "awb": lambda: r.choice(["EK", "RR", "CP", "AWB"]) + _rand_digits(r, 9) + r.choice(["IN", ""]),
        "phone": lambda: _phone(r),
        "email": lambda: r.choice(["claimdept", "lottery.office", "prize.manager", "winner.desk"]) + _rand_digits(r, 2) + "@" + r.choice(["gmail.com", "outlook.com", "yahoo.co.in"]),
        "scam_url": lambda: _scam_url(r),
        "apk_url": lambda: _scam_url(r).rstrip("/") + r.choice(["/app.apk", "/update.apk", "/download.apk"]),
        "upi_link": lambda: f"upi://pay?pa={_scam_upi(r)}&pn=Reward&am={r.randint(1, 9999)}&cu=INR",
        "tg_link": lambda: "https://t.me/" + r.choice(["earn", "profit", "vip", "task", "daily"]) + r.choice(["_india", "club", "group", "king"]) + _rand_digits(r, 2),
        "scam_upi": lambda: _scam_upi(r),
        "legit_upi": lambda: r.choice(NAMES).lower() + _rand_digits(r, 2) + "@" + r.choice(PSPS),
        "legit_url": lambda: r.choice(LEGIT_URLS),
    }


SLOT_RE = re.compile(r"\{(\w+)\}")
KEYBOARD_NEIGH = {"a": "s", "e": "r", "i": "o", "o": "p", "u": "y", "n": "m", "t": "y", "s": "d", "c": "v"}


def add_noise(r: random.Random, text: str) -> str:
    """Typos, dropped vowels, casing and spacing variations seen in real SMS."""
    words = text.split(" ")
    for i, w in enumerate(words):
        if len(w) > 4 and w.isalpha() and r.random() < 0.06:
            j = r.randrange(1, len(w) - 1)
            op = r.random()
            if op < 0.4:
                w = w[:j] + w[j + 1:]  # deletion
            elif op < 0.7:
                w = w[:j] + w[j + 1] + w[j] + w[j + 2:]  # swap
            else:
                w = w[:j] + KEYBOARD_NEIGH.get(w[j].lower(), w[j]) + w[j + 1:]
        words[i] = w
    text = " ".join(words)
    p = r.random()
    if p < 0.08:
        text = text.upper()
    elif p < 0.16:
        text = text.lower()
    if r.random() < 0.1:
        text = text.replace(". ", ".. ").replace("!", "!!")
    if r.random() < 0.08:
        text = text.replace(" you ", " u ").replace(" your ", " ur ").replace("please", "pls")
    return text


def fill(r: random.Random, template: str) -> str:
    slots = build_slots(r)
    cache: dict[str, str] = {}

    def repl(m: re.Match) -> str:
        key = m.group(1)
        # same bank / company / name inside one message; fresh values for amounts & urls
        if key in ("bank", "company", "name", "discom", "courier", "loan_app", "crypto_app") and key in cache:
            return cache[key]
        val = slots[key]()
        cache[key] = val
        return val

    return SLOT_RE.sub(repl, template)


def template_split(i: int) -> str:
    """Split by template index so a wording never appears in two splits."""
    if i % 4 == 3:
        return "test"
    if i % 8 == 1:
        return "val"
    return "train"


def synthetic_rows(r: random.Random) -> list[Record]:
    rows: list[Record] = []
    for cat, templates in TEMPLATES.items():
        n = PER_TEMPLATE.get(cat, DEFAULT_PER_TEMPLATE)
        for i, t in enumerate(templates):
            seen = set()
            for _ in range(n):
                text = fill(r, t)
                if r.random() < 0.6:
                    text = add_noise(r, text)
                if text in seen:
                    continue
                seen.add(text)
                rows.append(Record(text=text, label_binary=int(cat in SCAM_CATEGORIES), category=cat,
                                   source=NAME, split=template_split(i), group=f"{cat}:{i}"))
    return rows


def build() -> list[Record]:
    rows = synthetic_rows(random.Random(SEED))
    validate(rows)
    return rows


INFO = {
    "name": NAME,
    "version": GENERATOR_VERSION,
    "kind": "synthetic",
    "source_url": None,
    "licence": "MIT (generated by this repository)",
    "description": "Templated Indian SMS/WhatsApp messages (English + romanised Hindi) in 13 categories, "
                   "generated by ml/data/synthetic.py with a fixed seed. NOT real messages.",
    "labels": "label_binary + category (13 classes)",
    "split": "by template: index % 4 == 3 -> test, index % 8 == 1 -> val, else train",
}
