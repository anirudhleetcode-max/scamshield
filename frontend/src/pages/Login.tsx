import { useState } from "react";
import { useAuth } from "../lib/auth";
import { ShieldMark } from "../components/ShieldMark";
import Highlight from "../components/Highlight";
import type { Span } from "../lib/types";

const SPECIMEN = "Dear SBI customer, your account will be blocked today. Update KYC immediately at http://sbi-kyc.xyz or call 9123456780";
const find = (s: string) => SPECIMEN.indexOf(s);
const SPEC_SPANS: Span[] = [
  { start: find("will be blocked today"), end: find("will be blocked today") + 21, text: "", source: "rule", rule: "urgency" },
  { start: find("Update KYC"), end: find("Update KYC") + 10, text: "", source: "model", weight: 0.9 },
  { start: find("immediately"), end: find("immediately") + 11, text: "", source: "rule", rule: "urgency" },
  { start: find("http://sbi-kyc.xyz"), end: find("http://sbi-kyc.xyz") + 18, text: "", source: "rule", rule: "risky_link" },
  { start: find("9123456780"), end: SPECIMEN.length, text: "", source: "report", rule: "community_report" },
];

export default function Login() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(email, password);
      else await register(name, email, password);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <div className="auth-form">
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <ShieldMark size={26} />
          <span className="brand-name" style={{ fontSize: 18 }}>ScamShield</span>
        </div>
        <div>
          <h1>{mode === "login" ? "Sign in" : "Create an account"}</h1>
          <p className="muted" style={{ marginTop: 4 }}>
            Check a suspicious SMS, WhatsApp message, UPI ID or link before you act on it.
          </p>
        </div>
        <form onSubmit={submit} data-testid="auth-form">
          {mode === "register" && (
            <label className="field">
              <span>Name</span>
              <input className="input" name="name" required maxLength={60} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
            </label>
          )}
          <label className="field">
            <span>Email</span>
            <input className="input" name="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
          </label>
          <label className="field">
            <span>Password</span>
            <input className="input" name="password" type="password" required minLength={6} value={password}
                   onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} />
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="btn" disabled={busy} data-testid="auth-submit">
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>
        <div className="small" style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
          {mode === "login" ? (
            <span>New here? <button className="linkbtn" onClick={() => { setMode("register"); setError(null); }} data-testid="to-register">Create an account</button></span>
          ) : (
            <span>Have an account? <button className="linkbtn" onClick={() => { setMode("login"); setError(null); }}>Sign in</button></span>
          )}
          {mode === "login" && (
            <button className="linkbtn" onClick={() => { setEmail("demo@scamshield.app"); setPassword("demo1234"); }}>
              Use demo account
            </button>
          )}
        </div>
        <p className="note" style={{ marginTop: "auto" }}>
          Lost money already? Call <b className="mono">1930</b> or file at cybercrime.gov.in — the sooner, the better the chance of freezing it.
        </p>
      </div>
      <div className="auth-side">
        <h2>What a check looks like <span className="muted" style={{ textTransform: "none", letterSpacing: 0, fontWeight: 400 }}>(illustration)</span></h2>
        <div className="specimen">
          <div className="preview"><Highlight text={SPECIMEN} spans={SPEC_SPANS} /></div>
          <div className="specimen-foot">
            <span className="tag Scam">Scam · KYC / bank impersonation</span>
            <span className="mono" style={{ fontSize: 28, fontWeight: 500 }}>96<span className="muted" style={{ fontSize: 12 }}>/100</span></span>
          </div>
        </div>
        <ul className="small" style={{ margin: 0, paddingLeft: 18, color: "var(--ink-2)", display: "grid", gap: 4 }}>
          <li>Red underline: a rule matched (urgency, risky link, OTP request…)</li>
          <li>Red tint: words the model weighted toward “scam”</li>
          <li>Amber: a number other users have already reported</li>
        </ul>
      </div>
    </div>
  );
}
