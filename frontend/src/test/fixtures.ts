import type { Analysis } from "../lib/types";

export function analysis(over: Partial<Analysis> = {}): Analysis {
  return {
    score: 88,
    verdict: "Scam",
    status: "decided",
    abstain_reasons: [],
    scam_probability: 0.91,
    confidence_level: "high",
    thresholds: { suspicious: 60, scam: 71, uncertain_low: 0.2, uncertain_high: 0.8 },
    category: "kyc_bank",
    category_label: "KYC / bank impersonation",
    category_confidence: 0.93,
    top_categories: [
      { category: "kyc_bank", label: "KYC / bank impersonation", p: 0.93 },
      { category: "otp_harvest", label: "OTP harvesting", p: 0.04 },
    ],
    components: { model: 0.91, rules: 0.37, community: 0 },
    spans: [],
    flags: [
      { id: "urgency", label: "Creates urgency", hit: true, weight: 0.12 },
      { id: "asks_secret", label: "Asks for OTP", hit: false, weight: 0 },
    ],
    identifiers: [],
    advice: ["Call 1930 if you lost money."],
    model_version: "2.0.0",
    ...over,
  };
}

export function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}
