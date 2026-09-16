import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../lib/api";
import { Link } from "react-router-dom";
import { CATEGORY_LABELS, SAFE_CATEGORIES } from "../lib/types";
import type { ModelInfo } from "../lib/types";
import { SkeletonBlock } from "../components/Skeleton";
import { KIND_LABEL, fmtDay, pct } from "../lib/format";

type Day = { date: string; Safe: number; Suspicious: number; Scam: number };
type InsightsData = {
  days: number;
  per_day: Day[];
  categories: { category: string; label: string; n: number; avg_score: number }[];
  totals: { checks: number; flagged: number; scam: number; flagged_share: number; avg_score: number | null; my_reports: number;
    abstained?: number; demo_checks?: number };
  flags: { id: string; n: number }[];
  top_reported: { kind: string; value: string; reports: number; category: string; demo_only?: boolean }[];
};

const COLORS = { Safe: "#2f7a47", Suspicious: "#b8790b", Scam: "#c42a1f" } as const;
const FLAG_LABELS: Record<string, string> = {
  urgency: "Urgency / block threat", asks_secret: "Asks for OTP / PIN", upi_collect: "Collect request / PIN to receive",
  impersonation: "Poses as bank / officials", app_install: "Install an app / APK", threat: "Threats",
  money_lure: "Prize / easy money", fee_first: "Fee before payout", risky_link: "Risky link",
  personal_upi: "Suspicious UPI ID", non_official_sender: "Non-official sender", format_anomaly: "Odd formatting",
  community_report: "Reported identifier",
};

function DayTip({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number }[]; label?: string }) {
  if (!active || !payload || !label) return null;
  const total = payload.reduce((s, p) => s + p.value, 0);
  return (
    <div className="tip">
      <div style={{ marginBottom: 4 }}><b>{fmtDay(label)}</b><span>{total} checks</span></div>
      {[...payload].reverse().map((p) => <div key={p.name}><span>{p.name}</span><span>{p.value}</span></div>)}
    </div>
  );
}

export default function Insights() {
  const [data, setData] = useState<InsightsData | null>(null);
  const [model, setModel] = useState<ModelInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<InsightsData>("/api/insights?days=30").then(setData).catch((e) => setError(e.message));
    api<ModelInfo>("/api/model").then(setModel).catch(() => undefined);
  }, []);

  if (error) return <p className="error" role="alert">Could not load insights: {error}</p>;
  if (!data) return <><div className="page-head"><h1>Insights</h1></div><SkeletonBlock height={90} /><div className="section"><SkeletonBlock height={250} /></div></>;
  const t = data.totals;
  const maxCat = Math.max(1, ...data.categories.map((c) => c.n));
  const maxFlag = Math.max(1, ...data.flags.map((f) => f.n));
  const busiest = data.per_day.reduce((a, b) => (b.Safe + b.Suspicious + b.Scam > a.Safe + a.Suspicious + a.Scam ? b : a));

  return (
    <>
      <div className="page-head">
        <h1>Insights</h1>
        <p>Your last {data.days} days, plus what the community is reporting.</p>
        {!!t.demo_checks && <span className="right tag plain" data-testid="demo-data-tag">{t.demo_checks} of {t.checks} checks are demo seed data</span>}
      </div>

      <div className="stats" data-testid="stats">
        <div className="stat"><div className="label">Checks</div><div className="value">{t.checks}</div><div className="sub">last {data.days} days</div></div>
        <div className="stat"><div className="label">Flagged</div><div className="value">{pct(t.flagged_share)}</div><div className="sub">{t.flagged} suspicious or scam</div></div>
        <div className="stat"><div className="label">Scams caught</div><div className="value" style={{ color: "var(--scam)" }}>{t.scam}</div><div className="sub">score 70+</div></div>
        <div className="stat"><div className="label">Unsure</div><div className="value">{t.abstained ?? 0}</div><div className="sub">insufficient confidence · avg score {t.avg_score ?? "—"}</div></div>
        <div className="stat"><div className="label">Your reports</div><div className="value">{t.my_reports}</div><div className="sub">identifiers flagged</div></div>
      </div>

      <div className="panel section" data-testid="chart-per-day">
        <div className="panel-h">
          <h2>Checks per day</h2>
          <div className="right chart-legend" aria-label="Legend">
            {(["Scam", "Suspicious", "Safe"] as const).map((k) => <span key={k}><i style={{ background: COLORS[k] }} />{k}</span>)}
          </div>
        </div>
        <div className="panel-b" style={{ height: 250 }}>
          {t.checks === 0 ? <div className="empty"><strong>No checks in this period</strong>Saved checks will be charted here.</div> : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.per_day} margin={{ top: 4, right: 4, bottom: 0, left: -24 }} barCategoryGap={3}>
                <CartesianGrid vertical={false} stroke="#e4e1d8" />
                <XAxis dataKey="date" tickFormatter={fmtDay} tick={{ fontSize: 11, fill: "#75777d", fontFamily: "IBM Plex Mono" }}
                       tickLine={false} axisLine={{ stroke: "#b9b5a8" }} interval="preserveStartEnd" minTickGap={24} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#75777d", fontFamily: "IBM Plex Mono" }} tickLine={false} axisLine={false} />
                <Tooltip content={<DayTip />} cursor={{ fill: "rgba(23,24,27,.05)" }} />
                <Bar dataKey="Safe" stackId="v" fill={COLORS.Safe} stroke="#fbfaf7" strokeWidth={1} isAnimationActive={false} />
                <Bar dataKey="Suspicious" stackId="v" fill={COLORS.Suspicious} stroke="#fbfaf7" strokeWidth={1} isAnimationActive={false} />
                <Bar dataKey="Scam" stackId="v" fill={COLORS.Scam} stroke="#fbfaf7" strokeWidth={1} radius={[2, 2, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
        {t.checks > 0 && (
          <div className="legend">Busiest day: <span className="mono">{fmtDay(busiest.date)}</span> with {busiest.Safe + busiest.Suspicious + busiest.Scam} checks</div>
        )}
      </div>

      <div className="two section">
        <div className="panel" data-testid="chart-categories">
          <div className="panel-h"><h2>By pattern</h2><span className="right small muted">count · avg score</span></div>
          <div className="panel-b">
            {data.categories.length === 0 ? <div className="empty">Nothing yet.</div> : (
              <div className="catbars">
                {data.categories.map((c) => (
                  <div key={c.category} style={{ display: "contents" }}>
                    <span title={`average score ${c.avg_score}`}>{c.label}</span>
                    <div className="bar" title={`${c.n} checks, average score ${c.avg_score}`}>
                      <span className={SAFE_CATEGORIES.includes(c.category) ? "safe" : ""} style={{ width: `${(c.n / maxCat) * 100}%` }} />
                    </div>
                    <span className="mono" style={{ textAlign: "right" }}>{c.n}</span>
                  </div>
                ))}
              </div>
            )}
            <p className="note" style={{ marginTop: 12 }}>Dark bars are scam patterns, green bars are safe message types.</p>
          </div>
        </div>

        <div className="panel">
          <div className="panel-h"><h2>Red flags seen</h2></div>
          <div className="panel-b">
            {data.flags.length === 0 ? <div className="empty">No red flags in this period.</div> : (
              <div className="catbars">
                {data.flags.map((f) => (
                  <div key={f.id} style={{ display: "contents" }}>
                    <span>{FLAG_LABELS[f.id] ?? f.id}</span>
                    <div className="bar"><span style={{ width: `${(f.n / maxFlag) * 100}%`, background: "var(--scam)" }} /></div>
                    <span className="mono" style={{ textAlign: "right" }}>{f.n}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="two section">
        <div className="panel">
          <div className="panel-h"><h2>Most reported identifiers</h2><span className="right small muted">all users</span></div>
          {data.top_reported.length === 0 ? <div className="empty">No community reports yet.</div> : (
            <div className="table-wrap">
              <table className="t">
                <thead><tr><th>Identifier</th><th className="hide-sm">Type</th><th>Pattern</th><th className="n">Reports</th></tr></thead>
                <tbody>
                  {data.top_reported.map((r) => (
                    <tr key={r.kind + r.value}>
                      <td className="mono" style={{ overflowWrap: "anywhere" }}>{r.value}{r.demo_only && <div className="muted small" style={{ fontFamily: "var(--sans)" }}>demo seed data</div>}</td>
                      <td className="hide-sm muted">{KIND_LABEL[r.kind]}</td>
                      <td className="small">{CATEGORY_LABELS[r.category]}</td>
                      <td className="n">{r.reports}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="panel">
          <div className="panel-h"><h2>About the model</h2>{model?.card && <span className="right mono small muted">v{model.card.model_version}</span>}</div>
          <div className="panel-b" style={{ fontSize: 13, display: "grid", gap: 10 }} data-testid="model-summary">
            <p>TF-IDF word and character n-grams feed a calibrated logistic regression (scam or not) and a 13-way pattern classifier. Rule checks and community reports are combined with the model score.</p>
            {model?.card ? (
              <>
                <table className="cm">
                  <thead><tr><th style={{ textAlign: "left" }}>Test set</th><th>Precision</th><th>Recall</th><th>F1</th></tr></thead>
                  <tbody>
                    {Object.entries(model.card.metrics.main_model_test).map(([k, m]) => (
                      <tr key={k}>
                        <th style={{ textAlign: "left" }}>{k} <span className={model.card!.test_set_notes[k]?.startsWith("SYNTHETIC") ? "synthetic-tag" : "real-tag"}>
                          {model.card!.test_set_notes[k]?.startsWith("SYNTHETIC") ? "synthetic" : "real"}</span></th>
                        <td>{m.precision.toFixed(3)}</td><td>{m.recall.toFixed(3)}</td><td>{m.f1.toFixed(3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="small">The Indian scam examples and pattern labels are <b>synthetic</b> (generated from templates). Real labelled data is limited to English UK/Singapore SMS spam, so these numbers do not show accuracy on real Indian messages.</p>
                <p><Link to="/model">Full model card, baselines and limitations</Link></p>
              </>
            ) : <p className="muted">Model card unavailable.</p>}
          </div>
        </div>
      </div>
    </>
  );
}
