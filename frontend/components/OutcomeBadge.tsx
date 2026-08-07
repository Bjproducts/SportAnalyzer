export function OutcomeBadge({ value }: { value: boolean | null }) {
  if (value === null) {
    return <span className="outcome bg-violet-400/10 text-violet-300">— Missing</span>;
  }
  return value ? (
    <span className="outcome bg-emerald-400/10 text-emerald-300">✓ Hit</span>
  ) : (
    <span className="outcome bg-rose-400/10 text-rose-300">× Miss</span>
  );
}
