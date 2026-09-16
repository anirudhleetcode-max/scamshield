"""End-to-end journey through the real UI (headless Chromium).

Run via ./e2e/run_e2e.sh, or against already-running servers:
    E2E_BASE_URL=http://127.0.0.1:5173 python -m pytest e2e/test_e2e.py -q
"""
import os
import re
import uuid
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright

BASE = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5173")
SHOTS = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
EXTRA = Path(os.environ.get("E2E_EXTRA_SHOTS", "")) if os.environ.get("E2E_EXTRA_SHOTS") else None

KYC_SCAM = ("Dear SBI customer, your YONO account will be blocked today due to pending KYC. "
            "Update PAN immediately at http://sbi-kyc-verify.xyz/login or call our KYC officer.")
LEGIT_OTP = ("482913 is your OTP for a transaction of Rs 2,340.00 at Swiggy on HDFC Bank card XX4410. "
             "Valid for 10 mins. Do not share it with anyone.")
PHONE = "98" + str(uuid.uuid4().int)[:8]


@pytest.fixture(scope="module")
def page():
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        pg.set_default_timeout(15000)
        yield pg
        browser.close()


def nav(page: Page, label: str):
    page.locator("aside.side nav").get_by_role("link", name=label).click()


def test_full_journey(page: Page):
    # --- register
    page.goto(BASE)
    page.get_by_test_id("to-register").click()
    page.fill("input[name=name]", "E2E Tester")
    page.fill("input[name=email]", f"e2e_{uuid.uuid4().hex[:8]}@example.com")
    page.fill("input[name=password]", "secret123")
    page.get_by_test_id("auth-submit").click()
    expect(page.get_by_test_id("message-input")).to_be_visible()

    # --- KYC scam: live verdict without pressing anything
    page.get_by_test_id("message-input").fill(KYC_SCAM)
    page.get_by_test_id("sender-input").fill("+91 70112 23344")
    expect(page.get_by_test_id("verdict")).to_have_text("Scam")
    expect(page.get_by_test_id("category")).to_contain_text("KYC")
    marks = page.get_by_test_id("preview").locator("mark")
    expect(marks.first).to_be_visible()
    assert marks.count() >= 3
    assert page.get_by_test_id("preview").locator("mark[data-source=rule]").count() >= 1
    expect(page.locator('[data-flag=risky_link][data-hit=true]')).to_be_visible()
    expect(page.locator(".advice")).to_contain_text("1930")
    expect(page.get_by_test_id("confidence")).to_contain_text("high")
    page.get_by_test_id("save-check").click()
    expect(page.get_by_test_id("toast").last).to_contain_text("Scam")
    page.wait_for_timeout(300)
    page.screenshot(path=str(SHOTS / "check-scam.png"))

    # --- legit OTP -> Safe
    page.get_by_test_id("message-input").fill(LEGIT_OTP)
    page.get_by_test_id("sender-input").fill("VM-HDFCBK")
    expect(page.get_by_test_id("verdict")).to_have_text("Safe")
    expect(page.get_by_test_id("category")).to_contain_text("Legit transactional")
    page.get_by_test_id("save-check").click()
    expect(page.get_by_test_id("toast").last).to_contain_text("Safe")

    # --- a fragment the model should not judge -> abstains (not saved)
    page.get_by_test_id("message-input").fill("ok bhai")
    page.get_by_test_id("sender-input").fill("")
    expect(page.get_by_test_id("verdict")).to_have_text("Insufficient confidence")
    expect(page.locator("[data-reason=too_short]")).to_be_visible()

    # --- lookalike UPI ID
    nav(page, "UPI & Links")
    page.get_by_test_id("lookup-input").fill("sbi.refund@okaxls")
    page.get_by_test_id("lookup-submit").click()
    expect(page.get_by_test_id("lookup-risk")).to_have_text("High risk")
    expect(page.locator("[data-flag=lookalike_psp]")).to_contain_text("okaxis")
    expect(page.locator("[data-flag=bait_word]")).to_be_visible()
    page.screenshot(path=str(SHOTS / "upi-checker.png"))

    # --- report a phone number
    nav(page, "Reports")
    page.get_by_test_id("kind-phone").click()
    page.get_by_test_id("report-value").fill(PHONE)
    page.get_by_test_id("report-category").select_option("kyc_bank")
    page.get_by_test_id("report-submit").click()
    expect(page.get_by_test_id("report-msg")).to_contain_text("1 user has reported")
    expect(page.get_by_test_id("top-reported")).to_contain_text(PHONE)

    # --- a message containing that number now carries the community flag (not saved)
    nav(page, "Check")
    page.get_by_test_id("message-input").fill(f"Hello sir, your parcel is waiting. Call me on {PHONE} for delivery details.")
    expect(page.get_by_test_id("reported-tag")).to_have_text("1 report")
    expect(page.locator("[data-flag=community_report][data-hit=true]")).to_be_visible()
    assert page.get_by_test_id("preview").locator("mark[data-source=report]").count() == 1

    # --- history shows exactly the 2 saved checks
    nav(page, "History")
    expect(page.get_by_test_id("history-total")).to_have_text("2 checks")
    expect(page.get_by_test_id("history-row")).to_have_count(2)
    page.get_by_test_id("history-row").first.click()
    expect(page.locator("tr.open .preview")).to_contain_text("482913")

    # --- insights renders charts
    nav(page, "Insights")
    expect(page.get_by_test_id("stats")).to_contain_text("50%")
    expect(page.get_by_test_id("chart-per-day").locator(".recharts-bar-rectangle").first).to_be_attached()
    expect(page.get_by_test_id("chart-categories")).to_contain_text("KYC / bank impersonation")
    expect(page.get_by_test_id("model-summary")).to_contain_text("synthetic")

    # --- model card page labels synthetic data and shows limitations
    nav(page, "Model")
    expect(page.get_by_test_id("synthetic-warning")).to_be_visible()
    expect(page.get_by_test_id("datasets")).to_contain_text("uci_sms_spam")
    expect(page.get_by_test_id("datasets").get_by_test_id("synthetic-tag")).to_be_visible()
    expect(page.get_by_test_id("operating-points")).to_contain_text("score ≥")
    expect(page.get_by_test_id("limitations")).to_contain_text("synthetic")
    page.wait_for_timeout(300)
    page.screenshot(path=str(SHOTS / "model-card.png"))


def test_demo_account_insights(page: Page):
    """Seeded demo account (run_e2e.sh seeds it) for a realistic dashboard screenshot."""
    page.get_by_role("button", name="Sign out").first.click()
    page.goto(BASE)
    page.get_by_role("button", name="Use demo account").click()
    page.get_by_test_id("auth-submit").click()
    expect(page.get_by_test_id("message-input")).to_be_visible()
    expect(page.get_by_test_id("demo-banner")).to_be_visible()
    nav(page, "Insights")
    expect(page.get_by_test_id("demo-data-tag")).to_be_visible()
    expect(page.get_by_test_id("chart-per-day").locator(".recharts-bar-rectangle").first).to_be_attached()
    expect(page.get_by_test_id("stats")).to_contain_text(re.compile(r"\d+%"))
    page.wait_for_timeout(300)
    page.screenshot(path=str(SHOTS / "insights.png"))

    # --- delete with confirmation (demo history)
    nav(page, "History")
    expect(page.get_by_test_id("history-row").first).to_be_visible()
    total = page.get_by_test_id("history-total").inner_text()
    page.get_by_role("button", name="Delete check").first.click()
    page.get_by_role("button", name="Cancel").click()
    expect(page.get_by_test_id("history-total")).to_have_text(total)
    page.get_by_role("button", name="Delete check").first.click()
    page.get_by_test_id("confirm-delete").click()
    expect(page.get_by_test_id("toast").last).to_contain_text("deleted")
    expect(page.get_by_test_id("history-total")).not_to_have_text(total)

    # --- 375px mobile screenshot of a check
    nav(page, "Check")
    page.set_viewport_size({"width": 375, "height": 812})
    page.get_by_test_id("message-input").fill(KYC_SCAM)
    expect(page.get_by_test_id("verdict")).to_have_text("Scam")
    page.wait_for_timeout(300)
    page.screenshot(path=str(SHOTS / "mobile-check.png"), full_page=True)
    page.set_viewport_size({"width": 1440, "height": 900})

    if EXTRA:  # extra review shots (not part of the deliverable)
        EXTRA.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(EXTRA / "insights-full.png"), full_page=True)
        for path, name in [("/history", "history"), ("/reports", "reports"), ("/links", "links"), ("/model", "model")]:
            page.goto(BASE + path)
            page.wait_for_timeout(800)
            page.screenshot(path=str(EXTRA / f"{name}.png"), full_page=True)
        page.goto(BASE + "/")
        page.get_by_test_id("message-input").fill(KYC_SCAM + " Or call 9123456780")
        expect(page.get_by_test_id("verdict")).to_have_text("Scam")
        page.screenshot(path=str(EXTRA / "check-full.png"), full_page=True)
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(BASE + "/insights")
        expect(page.get_by_test_id("stats")).to_be_visible()
        page.wait_for_timeout(500)
        page.screenshot(path=str(EXTRA / "m-insights.png"), full_page=True)
        page.goto(BASE + "/links")
        page.get_by_test_id("lookup-input").fill("upi://pay?pa=cashback.help@ybl&pn=Reward&am=1999&tn=refund")
        page.get_by_test_id("lookup-submit").click()
        expect(page.get_by_test_id("lookup-risk")).to_be_visible()
        page.screenshot(path=str(EXTRA / "m-links.png"), full_page=True)
        page.get_by_role("button", name="Sign out").first.click()
        page.wait_for_timeout(300)
        page.screenshot(path=str(EXTRA / "m-login.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 900})
        page.screenshot(path=str(EXTRA / "login.png"))
