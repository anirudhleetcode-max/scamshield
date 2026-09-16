import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Trash2 } from "lucide-react";
import { api } from "../lib/api";
import type { Report, TopReported } from "../lib/types";
import { CATEGORY_LABELS, SCAM_CATEGORIES } from "../lib/types";
import { KIND_LABEL, ago } from "../lib/format";

type Page = { items: Report[]; next_cursor: string | null };
const PLACEHOLDER = { phone: "98765 43210", upi: "name@ybl", url: "suspicious-site.xyz/login" } as const;

export default function Reports() {
  const [params] = useSearchParams();
  const initialKind = (params.get("kind") as Report["kind"]) || "phone";
  const [kind, setKind] = useState<Report["kind"]>(["phone", "upi", "url"].includes(initialKind) ? initialKind : "phone");
  const [value, setValue] = useState(params.get("value") ?? "");
  const [category, setCategory] = useState("kyc_bank");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [mine, setMine] = useState<Report[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [top, setTop] = useState<TopReported[] | null>(null);

  const load = useCallback(async () => {
    const [p, t] = await Promise.all([
      api<Page>("/api/reports?limit=15"),
      api<{ items: TopReported[] }>("/api/reports/top?limit=10"),
    ]);
    setMine(p.items);
    setCursor(p.next_cursor);
    setTop(t.items);
  }, []);
  useEffect(() => { load().catch((e) => setMsg({ ok: false, text: e.message })); }, [load]);

  async function more() {
    if (!cursor) return;
    const p = await api<Page>(`/api/reports?limit=15&cursor=${cursor}`);
    setMine((m) => [...(m ?? []), ...p.items]);
    setCursor(p.next_cursor);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const r = await api<Report & { summary: { count: number } }>("/api/reports", {
        method: "POST", json: { kind, value, category, note: note || null },
      });
      setMsg({ ok: true, text: `Reported ${r.value}. ${r.summary.count} user${r.summary.count > 1 ? "s have" : " has"} reported it so far.` });
      setValue("");
      setNote("");
      await load();
    } catch (err) {
      setMsg({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    await api(`/api/reports/${id}`, { method: "DELETE" });
    setMine((m) => (m ?? []).filter((r) => r.id !== id));
    api<{ items: TopReported[] }>("/api/reports/top?limit=10").then((t) => setTop(t.items));
  }

  return (
    <>
      <div className="page-head">
        <h1>Community reports</h1>
        <p>Report a number, UPI ID or link that tried to scam you. Each account counts once per identifier.</p>
      </div>
      <div className="lookup-grid">
        <div>
          <form className="panel" onSubmit={submit} data-testid="report-form">
            <div className="panel-h"><h2>New report</h2></div>
            <div className="panel-b" style={{ display: "grid", gap: 12 }}>
              <div className="field">
                <span>Type</span>
                <div className="seg" role="group" aria-label="Identifier type">
                  {(["phone", "upi", "url"] as const).map((k) => (
                    <button type="button" key={k} aria-pressed={kind === k} onClick={() => setKind(k)} data-testid={`kind-${k}`}>
                      {KIND_LABEL[k]}
                    </button>
                  ))}
                </div>
              </div>
              <div className="row">
                <label className="field grow">
                  <span>{KIND_LABEL[kind]}</span>
                  <input className="input mono" required minLength={3} maxLength={500} value={value} data-testid="report-value"
                         placeholder={PLACEHOLDER[kind]} onChange={(e) => setValue(e.target.value)} />
                </label>
                <label className="field grow">
                  <span>What kind of scam</span>
                  <select className="select" value={category} onChange={(e) => setCategory(e.target.value)} data-testid="report-category">
                    {[...SCAM_CATEGORIES, "other"].map((c) => <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>)}
                  </select>
                </label>
              </div>
              <label className="field">
                <span>Note (optional, visible only to you)</span>
                <input className="input" maxLength={280} value={note} onChange={(e) => setNote(e.target.value)}
                       placeholder="e.g. Called pretending to be from SBI" />
              </label>
              <div className="row" style={{ alignItems: "center" }}>
                <button className="btn" disabled={busy || value.trim().length < 3} data-testid="report-submit">
                  {busy ? "Submitting…" : "Submit report"}
                </button>
                {msg && <span className={msg.ok ? "small" : "error"} role="status" data-testid="report-msg">{msg.text}</span>}
              </div>
            </div>
          </form>

          <div className="panel section">
            <div className="panel-h"><h2>Your reports</h2></div>
            {mine === null ? <div className="empty">Loading…</div> : mine.length === 0 ? (
              <div className="empty"><strong>No reports yet</strong>When something tries to scam you, report it here to warn others.</div>
            ) : (
              <div className="table-wrap">
                <table className="t">
                  <thead><tr><th>Type</th><th>Identifier</th><th className="hide-sm">Category</th><th className="n">Users</th><th className="hide-sm">When</th><th /></tr></thead>
                  <tbody>
                    {mine.map((r) => (
                      <tr key={r.id}>
                        <td className="muted">{KIND_LABEL[r.kind]}</td>
                        <td className="mono" style={{ overflowWrap: "anywhere" }}>{r.value}{r.note && <div className="muted small" style={{ fontFamily: "var(--sans)" }}>{r.note}</div>}</td>
                        <td className="hide-sm">{CATEGORY_LABELS[r.category]}</td>
                        <td className="n">{r.total_reports}</td>
                        <td className="hide-sm muted">{ago(r.created_at)}</td>
                        <td className="n"><button className="btn danger sm" aria-label={`Delete report ${r.value}`} onClick={() => remove(r.id)}><Trash2 size={13} /></button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {cursor && <div className="panel-b"><button className="btn ghost sm" onClick={more}>Load more</button></div>}
          </div>
        </div>

        <aside className="panel">
          <div className="panel-h"><h2>Most reported</h2><span className="right small muted">all users</span></div>
          {top === null ? <div className="empty">Loading…</div> : top.length === 0 ? (
            <div className="empty">No reports in the system yet.</div>
          ) : (
            <table className="t" data-testid="top-reported">
              <tbody>
                {top.map((t) => (
                  <tr key={t.kind + t.value}>
                    <td>
                      <div className="mono" style={{ overflowWrap: "anywhere" }}>{t.value}</div>
                      <div className="muted small">{KIND_LABEL[t.kind]} · {CATEGORY_LABELS[t.category]}</div>
                    </td>
                    <td className="n" style={{ fontSize: 18 }}>{t.reports}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </aside>
      </div>
    </>
  );
}
