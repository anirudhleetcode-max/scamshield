export type Verdict = "Safe" | "Suspicious" | "Scam";
export type Risk = "low" | "medium" | "high";

export type Span = {
  start: number;
  end: number;
  text: string;
  source: "model" | "rule" | "report";
  weight?: number;
  rule?: string;
};

export type Flag = {
  id: string;
  label: string;
  hit: boolean;
  weight: number;
  details?: string[];
  checked?: boolean;
};

export type Identifier = {
  kind: "phone" | "upi" | "url" | "upi_link";
  value: string;
  raw: string;
  start: number;
  end: number;
  reports: number;
  risk: Risk;
};

export type Analysis = {
  score: number;
  verdict: Verdict;
  category: string;
  category_label: string;
  category_confidence: number;
  top_categories: { category: string; label: string; p: number }[];
  components: { model: number; rules: number; community: number };
  spans: Span[];
  flags: Flag[];
  identifiers: Identifier[];
  advice: string[];
  model_version: string;
};

export type CheckItem = {
  id: string;
  text: string;
  sender: string | null;
  score: number;
  verdict: Verdict;
  category: string;
  category_label: string;
  flags_hit: string[];
  created_at: string;
  result?: Analysis;
};

export type LookupFlag = { id: string; label: string; severity: "high" | "medium" | "low" | "info" };

export type LookupResult = {
  kind: "phone" | "upi" | "url" | "upi_link";
  value: string;
  risk: Risk;
  flags: LookupFlag[];
  valid_format?: boolean;
  psp?: string | null;
  username?: string;
  handle?: string;
  host?: string | null;
  registrable_domain?: string;
  official_brand?: string | null;
  params?: { payee: string; name?: string; amount?: string; currency?: string; note?: string };
  reports: { count: number; categories: { category: string; n: number }[]; last_reported?: string | null };
  report_target: { kind: string; value: string | null };
};

export type Report = {
  id: string;
  kind: "phone" | "upi" | "url";
  value: string;
  category: string;
  note: string | null;
  created_at: string;
  total_reports?: number;
};

export type TopReported = { kind: string; value: string; reports: number; category: string; last_reported: string };

export const CATEGORY_LABELS: Record<string, string> = {
  kyc_bank: "KYC / bank impersonation",
  upi_collect: "UPI collect-request fraud",
  job_task: "Fake job / task scam",
  lottery_prize: "Lottery / prize",
  loan_app: "Loan app",
  delivery_courier: "Delivery / courier",
  electricity_bill: "Electricity bill disconnection",
  otp_harvest: "OTP harvesting",
  investment_crypto: "Investment / crypto",
  sextortion_threat: "Sextortion / threat",
  legit_transactional: "Legit transactional",
  promotional: "Promotional",
  personal: "Personal",
  other: "Other fraud",
};
export const SCAM_CATEGORIES = Object.keys(CATEGORY_LABELS).filter(
  (c) => !["legit_transactional", "promotional", "personal", "other"].includes(c),
);
export const SAFE_CATEGORIES = ["legit_transactional", "promotional", "personal"];
