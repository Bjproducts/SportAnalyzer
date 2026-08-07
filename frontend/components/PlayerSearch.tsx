"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";

import { apiGet } from "@/lib/api";
import type { PlayerSearchResponse } from "@/types/api";

export function PlayerSearch({ compact = false }: { compact?: boolean }) {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query.trim()), 220);
    return () => window.clearTimeout(timer);
  }, [query]);

  const result = useQuery({
    queryKey: ["players", debounced],
    queryFn: ({ signal }) =>
      apiGet<PlayerSearchResponse>("/players", {
        params: { q: debounced || undefined, page_size: compact ? 5 : 8 },
        signal,
      }),
    enabled: debounced.length >= 2,
  });

  return (
    <div className="relative w-full">
      <label htmlFor="player-search" className="sr-only">
        Search football players
      </label>
      <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-3 shadow-2xl shadow-black/20 backdrop-blur">
        <span className="text-lime" aria-hidden>
          ⌕
        </span>
        <input
          id="player-search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search player — Saka, Ødegaard, Havertz…"
          autoComplete="off"
          className="w-full bg-transparent text-sm text-white outline-none placeholder:text-slate-500"
        />
        {result.isFetching && <span className="h-2 w-2 animate-pulse rounded-full bg-lime" />}
      </div>

      {debounced.length >= 2 && (
        <div className="absolute z-40 mt-2 w-full overflow-hidden rounded-2xl border border-white/10 bg-ink-800/95 p-2 shadow-2xl backdrop-blur-xl">
          {result.isError && <p className="px-3 py-4 text-sm text-rose-300">Search unavailable.</p>}
          {!result.isFetching && result.data?.items.length === 0 && (
            <p className="px-3 py-4 text-sm text-slate-400">No players match “{debounced}”.</p>
          )}
          {result.data?.items.map((player) => (
            <Link
              key={player.id}
              href={`/players/${player.id}`}
              onClick={() => setQuery("")}
              className="flex items-center justify-between rounded-xl px-3 py-3 transition hover:bg-white/[0.07]"
            >
              <span>
                <span className="block text-sm font-semibold text-white">{player.display_name}</span>
                <span className="text-xs text-slate-400">
                  {player.current_team?.name ?? "Unattached"} · {player.primary_position ?? "Position unknown"}
                </span>
              </span>
              <span className="text-lime">→</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
