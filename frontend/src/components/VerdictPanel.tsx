import { Link } from "react-router-dom";
import { Check, X } from "lucide-react";
import type { Analysis, ConfidenceLevel, Flag, Verdict } from "../lib/types";
import { KIND_LABEL, pct } from "../lib/format";

type Band = Verdict | "Unsure";

export function ScoreMeter({ score, verdict, cutoffs }: { score: number; verdict: Band; cutoffs: [number, number] }) {
  const [s, c] = cutoffs;
  const track = `linear-gradient(to right, var(--safe-tint) 0 ${s}%, var(--sus-tint) ${s}% ${c}%, var(--scam-tint) ${c}% 100%)`;
  return (
    <div className="meter" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={score} aria-label="Risk score">
      <div className="meter-track" style={{ background: track }} />
      <div className={`meter-fill ${verdict}`} style={{ width: `${score}%` }} />
      {cutoffs.map((t) => (
        <span key={t}>
          <span className="meter-tick" style={{ left: `${t}%` }} />
          <span className="meter-scale" style={{ left: `${t}%`, top: 14 }}>{t}</span>
        </span>
      ))}
    </div>
  );
}

export function FlagList({ flags }: { flags: Flag[] }) {
  const sorted = [...flags].sort((a, b) => Number(b.hit) - Number(a.hit) || b.weight - a.weight);
  return (
    <ul className="flags" aria-label="Red flag checklist">
      {sorted.map((f) => (
        <li key={f.id} className={f.hit ? "hit" : "off"} data-flag={f.id} data-hit={f.hit}>
          <span className="ico">{f.hit ? <X size={15} strokeWidth={2.5} aria-label="found" /> : <Check size={15} aria-label="not found" />}</span>
          <span>
            {f.label}
            {f.id === "non_official_sender" && f.checked === false && <span className="muted small"> — add a sender to check</span>}
          </span>
          <span className="w">{f.hit ? `+${f.weight.toFixed(2)}` : ""}</span>
          {f.hit && f.details && f.details.length > 0 && (
            <span className="det">{f.details.map((d) => <div key={d}>{d}</div>)}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

const LEVELS: Record<ConfidenceLevel, { n: number; text: string }> = {
  high: { n: 3, text: "high" },
  medium: { n: 2, text: "medium — rules or reports overrode the model" },
  low: { n: 1, text: "low" },
};

export function Confidence({ level }: { level: ConfidenceLevel }) {
  const l = LEVELS[level];
  return (
    <span className="conf" data-testid="confidence">
      <span className="conf-dots" aria-hidden>{[1, 2, 3].map((i) => <i key={i} className={i <= l.n ? "on" : ""} />)}</span>
      {l.text}
    </span>
  );
}

export default function VerdictPanel({ a, pending }: { a: Analysis; pending?: boolean }) {
  const comp = a.components;
  const unsure = a.status === "insufficient_confidence";
  const band: Band = unsure ? "Unsure" : a.verdict;
  const cutoffs: [number, number] = [a.thresholds?.suspicious ?? 50, a.thresholds?.scam ?? 75];
  return (
    <div className={`panel ${pending ? "pending" : ""}`} data-testid="verdict-panel" aria-live="polite">
      <div className="verdict-top">
        <div>
          <div className="muted small">Verdict</div>
          <div className={`verdict-word ${band}`} data-testid="verdict">{unsure ? "Insufficient confidence" : a.verdict}</div>
          {unsure && <div className="small muted" data-testid="leaning">Score band would be: {a.verdict}</div>}
        </div>
        <div className="score" data-testid="score">{a.score}<small>/100</small></div>
        <ScoreMeter score={a.score} verdict={band} cutoffs={cutoffs} />
      </div>
      {unsure && (
        <div className="abstain" data-testid="abstain">
          <strong>Not enough to decide.</strong>
          <ul>{a.abstain_reasons.map((r) => <li key={r.id} data-reason={r.id}>{r.text}</li>)}</ul>
        </div>
      )}
      <dl className="meta-grid">
        <dt>Confidence</dt>
        <dd><Confidence level={a.confidence_level} /></dd>
        <dt>Model</dt>
        <dd className="small">
          <span className="mono">{pct(a.scam_probability, 1)}</span> calibrated scam probability
          <span className="muted"> · uncertain between {pct(a.thresholds.uncertain_low)}–{pct(a.thresholds.uncertain_high)}</span>
        </dd>
        <dt>Pattern</dt>
        <dd data-testid="category"><strong>{a.category_label}</strong> <span className="muted mono small">{pct(a.category_confidence)}</span>
          <span className="muted small"> · trained on synthetic examples</span></dd>
        <dt>Also close</dt>
        <dd className="small">
          {a.top_categories.filter((c) => c.category !== a.category).slice(0, 2)
            .map((c) => `${c.label} ${pct(c.p)}`).join(" · ") || "—"}
        </dd>
        <dt>Signals</dt>
        <dd>
          <div className="bars">
            <span>Model</span><div className="bar"><span style={{ width: pct(comp.model) }} /></div><span className="mono">{comp.model.toFixed(2)}</span>
            <span>Rules</span><div className="bar"><span style={{ width: pct(comp.rules) }} /></div><span className="mono">{comp.rules.toFixed(2)}</span>
            <span>Community</span><div className="bar"><span style={{ width: pct(comp.community) }} /></div><span className="mono">{comp.community.toFixed(2)}</span>
          </div>
        </dd>
      </dl>
      {a.identifiers.length > 0 && (
        <div style={{ borderTop: "1px solid var(--rule)" }}>
          <div className="panel-h" style={{ borderBottom: 0, paddingBottom: 0 }}><h2>Found in message</h2></div>
          <div className="table-wrap">
            <table className="t">
              <tbody>
                {a.identifiers.map((i) => (
                  <tr key={i.kind + i.value}>
                    <td className="muted">{KIND_LABEL[i.kind]}</td>
                    <td className="mono" style={{ overflowWrap: "anywhere" }}>{i.raw}</td>
                    <td>
                      {i.reports > 0
                        ? <span className="tag medium" data-testid="reported-tag">{i.reports} report{i.reports > 1 ? "s" : ""}</span>
                        : <span className={`tag ${i.risk}`}>{i.risk}</span>}
                    </td>
                    <td className="n">
                      {i.kind !== "upi_link" && (
                        <Link to={`/reports?kind=${i.kind}&value=${encodeURIComponent(i.value)}`} className="small">Report</Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <div className="panel-h" style={{ borderTop: "1px solid var(--rule)" }}>
        <h2>Red flags</h2>
        <span className="right mono small muted">{a.flags.filter((f) => f.hit).length} of {a.flags.length}</span>
      </div>
      <FlagList flags={a.flags} />
      <div className="advice">
        <h2>What to do</h2>
        <ol>
          {a.advice.map((t) => <li key={t}>{linkify(t)}</li>)}
        </ol>
      </div>
    </div>
  );
}

function linkify(t: string) {
  const parts = t.split(/(cybercrime\.gov\.in|1930)/);
  return parts.map((p, i) =>
    p === "cybercrime.gov.in" ? <a key={i} href="https://cybercrime.gov.in" target="_blank" rel="noreferrer">{p}</a>
      : p === "1930" ? <a key={i} href="tel:1930" className="mono">1930</a>
      : p,
  );
}
