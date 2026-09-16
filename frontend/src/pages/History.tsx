import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Trash2 } from "lucide-react";
import { api } from "../lib/api";
import type { CheckItem, Verdict } from "../lib/types";
import { CATEGORY_LABELS } from "../lib/types";
import { fmtDateTime } from "../lib/format";
import Highlight from "../components/Highlight";
import { FlagList } from "../components/VerdictPanel";

type Page = { items: CheckItem[]; next_cursor: string | null; total: number };

export default function History() {
  const [verdict, setVerdict] = useState<Verdict | "">("");
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<CheckItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [detail, setDetail] = useState<Record<string, CheckItem>>({});

  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 300);
    return () => clearTimeout(t);
  }, [q]);

  const qs = (c?: string | null) => {
    const p = new URLSearchParams({ limit: "20" });
    if (verdict) p.set("verdict", verdict);
    if (category) p.set("category", category);
    if (query.trim()) p.set("q", query.trim());
    if (c) p.set("cursor", c);
    return p.toString();
  };

  useEffect(() => {
    let alive = true;
    setItems(null);
    api<Page>(`/api/checks?${qs()}`)
      .then((p) => { if (alive) { setItems(p.items); setCursor(p.next_cursor); setTotal(p.total); setError(null); } })
      .catch((e) => alive && setError(e.message));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verdict, category, query]);

  async function more() {
    const p = await api<Page>(`/api/checks?${qs(cursor)}`);
    setItems((it) => [...(it ?? []), ...p.items]);
    setCursor(p.next_cursor);
  }

  async function toggle(id: string) {
    if (open === id) { setOpen(null); return; }
    setOpen(id);
    if (!detail[id]) {
      const d = await api<CheckItem>(`/api/checks/${id}`);
      setDetail((m) => ({ ...m, [id]: d }));
    }
  }

  async function remove(id: string) {
    await api(`/api/checks/${id}`, { method: "DELETE" });
    setItems((it) => (it ?? []).filter((x) => x.id !== id));
    setTotal((t) => t - 1);
    setOpen(null);
  }

  return (
    <>
      <div className="page-head">
        <h1>History</h1>
        <p>Messages you saved. Click a row to see the full analysis.</p>
        <span className="right mono small" data-testid="history-total">{total} check{total === 1 ? "" : "s"}</span>
      </div>
      <div className="row" style={{ marginBottom: 16, alignItems: "flex-end" }}>
        <div className="field">
          <span>Verdict</span>
          <div className="seg" role="group" aria-label="Filter by verdict">
            {(["", "Scam", "Suspicious", "Safe"] as const).map((v) => (
              <button key={v || "all"} aria-pressed={verdict === v} onClick={() => setVerdict(v)}>{v || "All"}</button>
            ))}
          </div>
        </div>
        <label className="field">
          <span>Category</span>
          <select className="select" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All categories</option>
            {Object.entries(CATEGORY_LABELS).filter(([k]) => k !== "other").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="field grow">
          <span>Search text</span>
          <input className="input" value={q} maxLength={80} placeholder="e.g. KYC, 98765, refund" onChange={(e) => setQ(e.target.value)} />
        </label>
      </div>

      {error && <p className="error" role="alert">{error}</p>}
      <div className="panel">
        {items === null ? <div className="empty">Loading…</div> : items.length === 0 ? (
          <div className="empty">
            <strong>{verdict || category || query ? "No checks match these filters" : "No saved checks yet"}</strong>
            {verdict || category || query ? "Try clearing a filter." : <>Go to <Link to="/">Check</Link>, paste a message and press “Save to history”.</>}
          </div>
        ) : (
          <div className="table-wrap">
            <table className="t" data-testid="history-table">
              <thead>
                <tr><th>When</th><th>Verdict</th><th className="n">Score</th><th className="hide-sm">Pattern</th><th>Message</th><th /></tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <Fragment key={c.id}>
                    <tr className={`click ${open === c.id ? "open" : ""}`} onClick={() => toggle(c.id)} data-testid="history-row"
                        tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter") toggle(c.id); }} aria-expanded={open === c.id}>
                      <td className="mono small" style={{ whiteSpace: "nowrap" }}>{fmtDateTime(c.created_at)}</td>
                      <td><span className={`tag ${c.verdict}`}>{c.verdict}</span></td>
                      <td className="n">{c.score}</td>
                      <td className="hide-sm small">{c.category_label}</td>
                      <td><div className="clip">{c.text}</div></td>
                      <td className="n">
                        <button className="btn danger sm" aria-label="Delete check" onClick={(e) => { e.stopPropagation(); remove(c.id); }}>
                          <Trash2 size={13} />
                        </button>
                      </td>
                    </tr>
                    {open === c.id && (
                      <tr className="open">
                        <td colSpan={6} style={{ padding: 0 }}>
                          {detail[c.id]?.result ? (
                            <div className="two" style={{ gap: 0 }}>
                              <div style={{ borderRight: "1px solid var(--rule)" }}>
                                <div className="preview"><Highlight text={c.text} spans={detail[c.id].result!.spans} /></div>
                                <div className="panel-b small muted" style={{ paddingTop: 0 }}>
                                  Sender: <span className="mono">{c.sender ?? "not given"}</span> · model {detail[c.id].result!.components.model.toFixed(2)} ·
                                  rules {detail[c.id].result!.components.rules.toFixed(2)} · community {detail[c.id].result!.components.community.toFixed(2)}
                                </div>
                              </div>
                              <FlagList flags={detail[c.id].result!.flags.filter((f) => f.hit)} />
                            </div>
                          ) : <div className="empty">Loading…</div>}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {cursor && items && items.length > 0 && (
          <div className="panel-b" style={{ borderTop: "1px solid var(--rule)" }}>
            <button className="btn ghost sm" onClick={more}>Load more</button>
            <span className="muted small" style={{ marginLeft: 12 }}>showing {items.length} of {total}</span>
          </div>
        )}
      </div>
    </>
  );
}
