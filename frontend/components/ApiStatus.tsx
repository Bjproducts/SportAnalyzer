"use client";

import { useQuery } from "@tanstack/react-query";

import { apiGet, apiBaseUrl, ApiError } from "@/lib/api";
import type { HealthResponse } from "@/types/api";

const DOT = {
  ok: "bg-emerald-400",
  degraded: "bg-rose-400",
  unknown: "bg-slate-600",
} as const;

/**
 * Live backend connectivity indicator.
 *
 * A 503 from /health is a *successful* diagnostic response, so it is rendered
 * as "degraded" with the real reason rather than as a generic failure.
 */
export function ApiStatus() {
  const { data, error, isPending } = useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      try {
        return await apiGet<HealthResponse>("/health");
      } catch (err) {
        if (err instanceof ApiError && err.status === 503) {
          return {
            status: "degraded",
            database: "unavailable",
            version: "unknown",
            environment: "unknown",
            uptime_seconds: 0,
          } satisfies HealthResponse;
        }
        throw err;
      }
    },
    refetchInterval: 30_000,
  });

  const state = isPending ? "unknown" : error ? "degraded" : (data?.status ?? "unknown");

  let message: string;
  if (isPending) {
    message = "Checking API…";
  } else if (error) {
    message = `API unreachable at ${apiBaseUrl()}`;
  } else if (data?.database !== "ok") {
    message = "API up · database unavailable";
  } else {
    message = `API healthy · ${data.environment} · v${data.version}`;
  }

  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.035] px-3 py-1.5 text-[10px] text-slate-500">
      <span
        aria-hidden
        className={`h-2 w-2 shrink-0 rounded-full ${DOT[state as keyof typeof DOT]} ${
          isPending ? "animate-pulse" : ""
        }`}
      />
      <span>{message}</span>
    </div>
  );
}
