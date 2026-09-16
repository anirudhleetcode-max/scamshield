from fastapi import APIRouter, Depends, HTTPException

from ..schemas import LookupIn
from ..security import current_user
from ..services import identifiers
from ..services.community import report_summary
from ..services.upi import analyze_upi, analyze_upi_link
from ..services.urls import analyze_url

router = APIRouter(prefix="/api/lookup", tags=["lookup"])


@router.post("")
async def lookup(body: LookupIn, user: dict = Depends(current_user)):
    """Check a single phone number, UPI ID, URL or upi:// link."""
    value = body.value.strip()
    kind = body.kind or identifiers.detect_kind(value)
    if kind == "phone":
        norm = identifiers.norm_phone(value)
        if not norm:
            raise HTTPException(422, "Not a valid Indian mobile number")
        result = {"kind": "phone", "value": norm, "risk": "low", "flags": [
            {"id": "mobile", "severity": "info",
             "label": "Personal mobile number - banks and companies send SMS from registered headers like VM-HDFCBK"}]}
    elif kind == "upi":
        result = analyze_upi(value)
    elif kind == "upi_link":
        result = analyze_upi_link(value)
    else:
        result = analyze_url(value)

    # community reports for the identifier itself (and for the payee of a upi:// link)
    report_kind, report_value = kind, result.get("value")
    if kind == "url":
        report_value = identifiers.norm_url(value)
    elif kind == "upi_link":
        report_kind, report_value = "upi", (result.get("params") or {}).get("payee", "").lower()
    reports = await report_summary(report_kind, report_value) if report_value else {"count": 0, "categories": []}
    result["reports"] = reports
    result["report_target"] = {"kind": report_kind, "value": report_value}
    if reports["count"]:
        result["flags"].insert(0, {"id": "community_report", "severity": "high",
                                   "label": f"Reported as fraud by {reports['count']} user{'s' if reports['count'] != 1 else ''}"})
        result["risk"] = "high"
    return result
