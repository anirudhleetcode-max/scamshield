export function KindTag({ kind }: { kind: string }) {
  return kind === "synthetic"
    ? <span className="synthetic-tag" data-testid="synthetic-tag">synthetic</span>
    : <span className="real-tag">real</span>;
}
