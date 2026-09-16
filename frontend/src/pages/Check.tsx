import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Save } from "lucide-react";
import { api } from "../lib/api";
import type { Analysis, CheckItem } from "../lib/types";
import Highlight, { HighlightLegend } from "../components/Highlight";
import VerdictPanel from "../components/VerdictPanel";

const SAMPLES: { label: string; text: string; sender?: string }[] = [
  { label: "KYC block", sender: "+91 70112 23344",
    text: "Dear SBI customer, your YONO account will be blocked today due to pending KYC. Update PAN immediately: http://sbi-kyc-verify.xyz/login" },
  { label: "OLX buyer", text: "Hi, I am the buyer for your sofa. I sent a collect request of Rs 8,500 from sbi.refund24@ybl. Please accept and enter UPI PIN to receive money." },
  { label: "Task job", text: "Hello! Part time job, earn Rs 3,000 daily by liking YouTube videos. Join our telegram https://t.me/earn_club21 now, limited seats." },
  { label: "Bank OTP", sender: "VM-HDFCBK",
    text: "482913 is your OTP for a transaction of Rs 2,340.00 at Swiggy on HDFC Bank card XX4410. Valid for 10 mins. Do not share it with anyone." },
  { label: "Delivery", sender: "JD-DLVRY",
    text: "Your Myntra order #OD4412098812 is out for delivery today. The delivery agent will call you before arriving." },
];

export default function Check() {
  const [text, setText] = useState("");
  const [sender, setSender] = useState("");
  const [result, setResult] = useState<{ text: string; a: Analysis } | null>(null);
  const [analysing, setAnalysing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<CheckItem | null>(null);
  const seq = useRef(0);

  // live analysis, debounced 400ms; stale responses are discarded by sequence number
  useEffect(() => {
    const body = text.trim();
    if (!body) { setResult(null); setError(null); setAnalysing(false); return; }
    const id = ++seq.current;
    setAnalysing(true);
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      api<Analysis>("/api/check/analyze", { method: "POST", json: { text, sender: sender || null }, signal: ctrl.signal })
        .then((r) => { if (id === seq.current) { setResult({ text, a: r }); setError(null); } })
        .catch((e) => { if (id === seq.current && e.name !== "AbortError") setError(e.message); })
        .finally(() => { if (id === seq.current) setAnalysing(false); });
    }, 400);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [text, sender]);

  useEffect(() => {
    if (!saved) return;
    const t = setTimeout(() => setSaved(null), 5000);
    return () => clearTimeout(t);
  }, [saved]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setSaving(true);
    try {
      const item = await api<CheckItem>("/api/checks", { method: "POST", json: { text, sender: sender || null } });
      setSaved(item);
      if (item.result) setResult({ text, a: item.result });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const shown = result && text.trim() ? result.a : null;

  return (
    <>
      <div className="page-head">
        <h1>Check a message</h1>
        <p>Paste an SMS, WhatsApp message or payment request. Analysis runs as you type.</p>
      </div>
      <div className="check-grid">
        <div>
          <form className="panel" onSubmit={save}>
            <div className="panel-h">
              <h2>Message</h2>
              <span className="right counter">{text.length}/2000</span>
            </div>
            <div className="panel-b" style={{ display: "grid", gap: 12 }}>
              <label className="field">
                <span className="sr-only">Message text</span>
                <textarea
                  className="textarea"
                  data-testid="message-input"
                  value={text}
                  maxLength={2000}
                  placeholder="e.g. Dear customer, your account will be blocked today. Update KYC at …"
                  onChange={(e) => setText(e.target.value)}
                  autoFocus
                />
              </label>
              <div className="row">
                <label className="field grow">
                  <span>Sender (optional)</span>
                  <input className="input mono" data-testid="sender-input" value={sender} maxLength={40}
                         placeholder="VM-HDFCBK or +91 98xxx xxxxx" onChange={(e) => setSender(e.target.value)} />
                </label>
                <button className="btn" type="submit" disabled={!text.trim() || saving} data-testid="save-check">
                  <Save size={15} aria-hidden /> {saving ? "Saving…" : "Save to history"}
                </button>
              </div>
              <div className="samples">
                <span className="muted small">Try:</span>
                {SAMPLES.map((s) => (
                  <button type="button" className="chip" key={s.label}
                          onClick={() => { setText(s.text); setSender(s.sender ?? ""); }}>
                    {s.label}
                  </button>
                ))}
                {text && <button type="button" className="linkbtn small" onClick={() => { setText(""); setSender(""); }}>Clear</button>}
              </div>
            </div>
          </form>

          <div className="panel section">
            <div className="panel-h">
              <h2>What drove the score</h2>
              <span className="right small muted">{analysing ? "analysing…" : shown ? `${shown.spans.length} highlighted` : ""}</span>
            </div>
            <div className="preview" data-testid="preview">
              {shown && result ? <Highlight text={result.text} spans={shown.spans} /> : <span className="muted">Highlighted phrases will appear here.</span>}
            </div>
            <HighlightLegend />
          </div>
          {error && <p className="error section" role="alert">{error}</p>}
        </div>

        <div>
          {shown ? (
            <VerdictPanel a={shown} pending={analysing} />
          ) : (
            <div className="panel placeholder">
              <div className="score">--<small>/100</small></div>
              <p style={{ marginTop: 12 }}>
                {analysing ? "Analysing…" : "No message yet. The verdict, a 0–100 risk score, the red-flag checklist and advice will show here."}
              </p>
              <p className="small" style={{ marginTop: 12 }}>
                Scores under 35 are <b style={{ color: "var(--safe)" }}>Safe</b>, 35–69 <b style={{ color: "var(--sus)" }}>Suspicious</b>, 70 and above <b style={{ color: "var(--scam)" }}>Scam</b>.
              </p>
            </div>
          )}
        </div>
      </div>
      {saved && (
        <div className="toast" role="status" data-testid="saved-toast">
          Saved — {saved.verdict}, score {saved.score}
          <Link to="/history">View history</Link>
        </div>
      )}
    </>
  );
}
