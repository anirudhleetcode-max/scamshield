const dtf = new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
const df = new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short" });

export const fmtDateTime = (iso: string) => dtf.format(new Date(iso));
export const fmtDay = (isoDate: string) => df.format(new Date(isoDate + "T00:00:00"));
export const pct = (x: number, digits = 0) => `${(x * 100).toFixed(digits)}%`;

export function ago(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export const KIND_LABEL: Record<string, string> = { phone: "Phone", upi: "UPI ID", url: "Link", upi_link: "UPI link" };
