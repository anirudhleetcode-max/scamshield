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

export type AnalysisStatus = "decided" | "insufficient_confidence";
export type ConfidenceLevel = "high" | "medium" | "low";

export type Analysis = {
  score: number;
  verdict: Verdict;
  status: AnalysisStatus;
  abstain_reasons: { id: string; text: string }[];
  scam_probability: number;
  confidence_level: ConfidenceLevel;
  thresholds: { suspicious: number; scam: number; uncertain_low: number; uncertain_high: number };
  input_quality?: { n_chars: number; n_words: number; letters: number; non_latin_ratio: number; url_ratio: number };
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
  status?: AnalysisStatus;
  demo?: boolean;
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

export type TopReported = {
  kind: string; value: string; reports: number; category: string; last_reported: string; demo_only?: boolean;
};

type Prf = { precision: number; recall: number; f1: number };
export type ModelMetrics = Prf & { n: number; roc_auc: number | null; pr_auc: number | null; brier: number | null; ece: number | null };

export type ModelCard = {
  model_name: string;
  model_version: string;
  created_at: string;
  experiment_run: string;
  git_commit: string | null;
  intended_use: string;
  pipeline: string[];
  training_data: {
    datasets: { name: string; kind: "synthetic" | "real"; version: string; source_url: string | null; licence: string;
      processed_sha256: string | null; counts: { total: number }; description: string; used_for?: string[] }[];
    train_rows: number;
    val_rows: number;
    contains_synthetic: boolean;
    note: string;
  };
  preprocessing_version: string;
  libraries: Record<string, string>;
  python: string;
  operating_points: {
    model_threshold: number; suspicious_score: number; scam_score: number;
    uncertain_band: { low: number; high: number };
    rules: Record<string, string>;
    val_selective: { coverage: number; selective_accuracy: number | null; target_accuracy: number; target_met?: boolean };
  };
  metrics: {
    main_model_test: Record<string, ModelMetrics>;
    full_system_test: Record<string, { flag_if_suspicious_or_scam: Prf; flag_if_scam: Prf }>;
    category_head_test: Record<string, { accuracy: number; macro_f1: number; n: number }>;
    baselines_test_at_val_threshold: Record<string, Record<string, Prf & { pr_auc: number | null }>>;
    calibration: Record<string, Record<string, { brier: number | null; ece: number | null }>>;
  };
  test_set_notes: Record<string, string>;
  limitations: string[];
  artifact?: { file: string; size_kb: number };
};

export type ModelInfo = { available: boolean; loaded: boolean; error: string | null; model_version?: string; card: ModelCard | null };

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
