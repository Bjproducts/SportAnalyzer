export function LoadingState({ label = "Loading analytics" }: { label?: string }) {
  return (
    <div className="panel flex min-h-48 items-center justify-center gap-3 text-sm text-slate-400">
      <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-lime" />
      {label}
    </div>
  );
}

export function ErrorState({ message = "This data could not be loaded." }: { message?: string }) {
  return (
    <div className="rounded-2xl border border-rose-400/20 bg-rose-400/[0.06] px-5 py-8 text-sm text-rose-200">
      {message}
    </div>
  );
}
