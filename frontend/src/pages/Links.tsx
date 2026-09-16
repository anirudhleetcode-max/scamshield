import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Info, Search, ShieldCheck } from "lucide-react";
import { api } from "../lib/api";
import type { LookupResult } from "../lib/types";
import { CATEGORY_LABELS } from "../lib/types";
import { KIND_LABEL, fmtDateTime } from "../lib/format";

const EXAMPLES = [
  "sbi-refund@ybl",
  "rahul.sharma@okaxis",
  "priya@okaxls",
  "upi://pay?pa=cashback.help@ybl&pn=Reward&am=1999&tn=refund",
  "http://hdfcbamk.com/login",
  "bit.ly/3kycupd",
  "https://www.onlinesbi.sbi",
];
const HANDLES = ["okaxis", "oksbi", "okhdfcbank", "okicici", "ybl", "ibl", "axl", "paytm", "upi", "apl"];
const RISK_WORD = { high: "High risk", medium: "Be careful", low: "No issues found" } as const;

export default function Links() {
  const [value, setValue] = useState("");
  const [res, setRes] = useState<LookupResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(v: string) {
    if (v.trim().length < 3) return;
    setLoading(true);
    setError(null);
    try {
      setRes(await api<LookupResult>("/api/lookup", { method: "POST", json: { value: v.trim() } }));
    } catch (e) {
      setRes(null);
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const target = res?.report_target;
  return (
    <>
      <div className="page-head">
        <h1>UPI IDs &amp; links</h1>
        <p>Check a UPI ID, a <span className="mono">upi://</span> payment link, a web link or a phone number.</p>
      </div>
      <div className="lookup-grid">
        <div>
          <form className="panel" onSubmit={(e) => { e.preventDefault(); run(value); }}>
            <div className="panel-b">
              <div className="row">
                <label className="field grow">
                  <span>UPI ID, link or number</span>
                  <input className="input mono" data-testid="lookup-input" value={value} maxLength={500}
                         placeholder="name@okaxis · https://… · upi://pay?pa=… · 98xxxxxxxx"
                         onChange={(e) => setValue(e.target.value)} />
                </label>
                <button className="btn" disabled={loading || value.trim().length < 3} data-testid="lookup-submit">
                  <Search size={15} aria-hidden /> {loading ? "Checking…" : "Check"}
                </button>
              </div>
              <div className="samples" style={{ marginTop: 10 }}>
                <span className="muted small">Examples:</span>
                {EXAMPLES.map((x) => (
                  <button key={x} type="button" className="chip mono" onClick={() => { setValue(x); run(x); }}>
                    {x.length > 34 ? x.slice(0, 32) + "…" : x}
                  </button>
                ))}
              </div>
            </div>
          </form>
          {error && <p className="error section" role="alert">{error}</p>}

          {res && (
            <div className="panel section" data-testid="lookup-result">
              <div className="panel-h">
                <span className={`tag ${res.risk}`} data-testid="lookup-risk">{RISK_WORD[res.risk]}</span>
                <span className="muted small">{KIND_LABEL[res.kind]}</span>
                {target?.value && target.kind !== "upi_link" && (
                  <Link className="right btn ghost sm"
                        to={`/reports?kind=${target.kind}&value=${encodeURIComponent(target.value)}`}>
                    Report as fraud
                  </Link>
                )}
              </div>
              <div className="panel-b">
                <div className="big-id">{res.value}</div>
                <ul className="flags" style={{ margin: "12px -16px 0" }}>
                  {res.flags.length === 0 && (
                    <li className="off"><span className="ico"><ShieldCheck size={15} /></span><span>No red flags in the format. This does not prove the owner is genuine.</span><span /></li>
                  )}
                  {res.flags.map((f) => (
                    <li key={f.id + f.label} className={f.severity === "info" || f.severity === "low" ? "off" : "hit"} data-flag={f.id}>
                      <span className="ico">
                        {f.severity === "info" ? <Info size={15} style={{ color: "var(--ink-3)" }} /> : <AlertTriangle size={15} />}
                      </span>
                      <span>{f.label}</span>
                      <span className="w">{f.severity}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="panel-b" style={{ borderTop: "1px solid var(--rule)" }}>
                <dl className="kv">
                  {res.kind === "upi" && res.valid_format && <>
                    <dt>Name part</dt><dd>{res.username}</dd>
                    <dt>Handle</dt><dd>@{res.handle}</dd>
                    <dt>Provider</dt><dd>{res.psp ?? "unknown"}</dd>
                  </>}
                  {res.kind === "url" && <>
                    <dt>Host</dt><dd>{res.host ?? "—"}</dd>
                    <dt>Domain</dt><dd>{res.registrable_domain ?? "—"}</dd>
                    <dt>Official site</dt><dd>{res.official_brand ?? "not on our list"}</dd>
                  </>}
                  {res.kind === "upi_link" && res.params && <>
                    <dt>Pays to</dt><dd>{res.params.payee || "—"}</dd>
                    <dt>Payee name</dt><dd>{res.params.name ?? "—"}</dd>
                    <dt>Amount</dt><dd>{res.params.amount ? `${res.params.amount} ${res.params.currency ?? ""}` : "not fixed"}</dd>
                    <dt>Note</dt><dd>{res.params.note ?? "—"}</dd>
                  </>}
                  <dt>Community</dt>
                  <dd data-testid="lookup-reports">
                    {res.reports.count
                      ? <>{res.reports.count} report{res.reports.count > 1 ? "s" : ""} · {res.reports.categories.map((c) => CATEGORY_LABELS[c.category] ?? c.category).join(", ")}
                          {res.reports.last_reported && <span className="muted"> · last {fmtDateTime(res.reports.last_reported)}</span>}</>
                      : "no reports yet"}
                  </dd>
                </dl>
              </div>
            </div>
          )}
          {!res && !error && (
            <div className="panel section empty">
              <strong>Nothing checked yet</strong>
              Paste something above or pick an example.
            </div>
          )}
        </div>

        <aside className="panel">
          <div className="panel-h"><h2>How to read a UPI ID</h2></div>
          <div className="panel-b" style={{ display: "grid", gap: 12, fontSize: 13 }}>
            <p><span className="mono">name</span><b className="mono">@</b><span className="mono">handle</span> — the handle after <span className="mono">@</span> tells you which app or bank issued it. Common handles:</p>
            <div className="handles">
              {HANDLES.map((h) => <code key={h} onClick={() => setValue(`yourname@${h}`)}>@{h}</code>)}
            </div>
            <p>A company never collects a refund, KYC fee or prize tax through a personal-looking ID such as <span className="mono">sbi.refund24@ybl</span>.</p>
            <p><b>Receiving money never needs your PIN.</b> If an app asks for your UPI PIN, you are sending money.</p>
            <p>A <span className="mono">upi://pay</span> link or QR code always pays <i>out</i> of your account.</p>
            <p className="note">Format checks cannot prove an ID is genuine — they catch the common tricks.</p>
          </div>
        </aside>
      </div>
    </>
  );
}
