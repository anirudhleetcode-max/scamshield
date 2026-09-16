export function ShieldMark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="3" fill="#17181b" />
      <path d="M16 5l9 3.5v6.8c0 5.6-3.8 10-9 11.7-5.2-1.7-9-6.1-9-11.7V8.5L16 5z" fill="none" stroke="#f6f5f1" strokeWidth="2" />
      <rect x="11" y="15" width="10" height="2.4" fill="#c42a1f" />
    </svg>
  );
}
