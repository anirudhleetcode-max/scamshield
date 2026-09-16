import type { Span } from "../lib/types";

const PRIORITY = { report: 3, rule: 2, model: 1 } as const;
const RULE_TITLES: Record<string, string> = {
  urgency: "Urgency / threat of block",
  asks_secret: "Asks for OTP / PIN",
  upi_collect: "Collect request / PIN to receive",
  impersonation: "Claims to be bank or officials",
  app_install: "Asks to install an app",
  threat: "Threat",
  money_lure: "Too-good-to-be-true offer",
  fee_first: "Fee before payout",
  risky_link: "Risky link",
  personal_upi: "Suspicious UPI ID",
  format_anomaly: "Odd formatting",
  community_report: "Reported by other users",
};

type Seg = { text: string; span: Span | null };

/** Splits text into segments; where spans overlap the highest-priority source wins. */
export function segments(text: string, spans: Span[]): Seg[] {
  const owner: (Span | null)[] = new Array(text.length).fill(null);
  for (const s of spans) {
    for (let i = Math.max(0, s.start); i < Math.min(text.length, s.end); i++) {
      const cur = owner[i];
      if (!cur || PRIORITY[s.source] > PRIORITY[cur.source] ||
          (s.source === cur.source && (s.weight ?? 1) > (cur.weight ?? 1))) owner[i] = s;
    }
  }
  const out: Seg[] = [];
  for (let i = 0; i < text.length; i++) {
    const last = out[out.length - 1];
    if (last && last.span === owner[i]) last.text += text[i];
    else out.push({ text: text[i], span: owner[i] });
  }
  return out;
}

function title(s: Span) {
  if (s.source === "model") return `Model weight ${(s.weight ?? 0).toFixed(2)} toward scam`;
  return RULE_TITLES[s.rule ?? ""] ?? "Rule";
}

export default function Highlight({ text, spans }: { text: string; spans: Span[] }) {
  return (
    <>
      {segments(text, spans).map((seg, i) =>
        seg.span ? (
          <mark
            key={i}
            className={`hl hl-${seg.span.source}`}
            data-source={seg.span.source}
            style={seg.span.source === "model" ? ({ "--w": seg.span.weight ?? 0.5 } as React.CSSProperties) : undefined}
            title={title(seg.span)}
          >
            {seg.text}
          </mark>
        ) : (
          <span key={i}>{seg.text}</span>
        ),
      )}
    </>
  );
}

export function HighlightLegend() {
  return (
    <div className="legend" aria-label="Highlight legend">
      <span><i style={{ background: "rgba(196,42,31,.26)" }} />model weight (darker = stronger)</span>
      <span><i style={{ background: "rgba(196,42,31,.10)", boxShadow: "inset 0 -2px 0 #c42a1f" }} />red-flag rule</span>
      <span><i style={{ background: "#f5e5c6", boxShadow: "inset 0 -2px 0 #a86400" }} />reported by users</span>
    </div>
  );
}
