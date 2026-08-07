"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { apiGet } from "@/lib/api";
import { formatMatchDate, formatNumber, formatPercent } from "@/lib/utils";
import type {
  PlayerMatchesResponse,
  PlayerSplitsResponse,
  PlayerStreaksResponse,
  PlayerSummaryResponse,
  Venue,
} from "@/types/api";

import { ErrorState, LoadingState } from "./LoadingState";
import { MatchTable } from "./MatchTable";
import { Panel, StatCard } from "./StatCard";
import { SotTrendChart } from "./SotTrendChart";

export function PlayerAnalyticsView({ playerId }: { playerId: number }) {
  const router = useRouter();
  const search = useSearchParams();
  const venue = (search.get("venue") as Venue | null) ?? "all";
  const lastN = search.get("last_n") ?? "10";
  const startsOnly = search.get("starts_only") === "true";
  const page = Number(search.get("page") ?? 1);
  const filters = { venue, last_n: lastN === "season" ? undefined : Number(lastN), starts_only: startsOnly };

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(search.toString());
    next.set(key, value);
    if (key !== "page") next.set("page", "1");
    router.replace(`?${next.toString()}`, { scroll: false });
  };

  const summary = useQuery({
    queryKey: ["player-summary", playerId, filters],
    queryFn: ({ signal }) => apiGet<PlayerSummaryResponse>(`/players/${playerId}/sot-summary`, { params: filters, signal }),
  });
  const matches = useQuery({
    queryKey: ["player-matches", playerId, filters, page],
    queryFn: ({ signal }) =>
      apiGet<PlayerMatchesResponse>(`/players/${playerId}/matches`, {
        params: { ...filters, page, page_size: 20 },
        signal,
      }),
  });
  const splits = useQuery({
    queryKey: ["player-splits", playerId, filters],
    queryFn: ({ signal }) => apiGet<PlayerSplitsResponse>(`/players/${playerId}/splits`, { params: filters, signal }),
  });
  const streaks = useQuery({
    queryKey: ["player-streaks", playerId, filters],
    queryFn: ({ signal }) => apiGet<PlayerStreaksResponse>(`/players/${playerId}/streaks`, { params: filters, signal }),
  });

  if (summary.isPending || matches.isPending) return <LoadingState label="Building player profile" />;
  if (summary.isError || matches.isError || !summary.data || !matches.data) {
    return <ErrorState message="This player profile could not be loaded. Check that provider data has been imported." />;
  }

  const player = summary.data.player;
  const metrics = summary.data.summary;
  const one = metrics.threshold_rates["1"];
  const two = metrics.threshold_rates["2"];

  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-3xl border border-white/10 bg-ink-800 p-6 md:p-8">
        <div className="absolute -right-16 -top-24 h-72 w-72 rounded-full bg-lime/10 blur-3xl" />
        <div className="relative flex flex-col justify-between gap-6 md:flex-row md:items-end">
          <div>
            <Link href="/" className="mb-5 inline-block text-xs font-medium uppercase tracking-[0.14em] text-lime">← Player search</Link>
            <p className="eyebrow">{player.current_team ? <Link href={`/teams/${player.current_team.id}`} className="hover:text-lime">{player.current_team.name}</Link> : "Unattached"} · {player.nationality ?? "Nationality unknown"}</p>
            <h1 className="mt-2 text-4xl font-semibold tracking-[-0.05em] text-white md:text-6xl">{player.display_name}</h1>
            <p className="mt-3 text-sm text-slate-400">{player.primary_position ?? player.position_group} · Competitive matches only</p>
          </div>
          <div className="rounded-2xl border border-lime/20 bg-lime/[0.06] px-5 py-4 text-right">
            <p className="eyebrow">Current streak</p>
            <p className="mt-1 text-4xl font-semibold text-lime tabular">{streaks.data?.streak.current ?? "—"}</p>
            <p className="text-xs text-slate-400">consecutive valid starts</p>
          </div>
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.03] p-2">
        <FilterGroup label="Venue" values={["all", "home", "away"]} active={venue} onSelect={(value) => update("venue", value)} />
        <span className="hidden h-7 w-px bg-white/10 md:block" />
        <FilterGroup label="Window" values={["5", "10", "20", "season"]} active={lastN} onSelect={(value) => update("last_n", value)} display={(v) => (v === "season" ? "Full season" : `Last ${v}`)} />
        <label className="ml-auto flex cursor-pointer items-center gap-2 rounded-xl px-3 py-2 text-xs text-slate-300">
          <input type="checkbox" checked={startsOnly} onChange={(event) => update("starts_only", String(event.target.checked))} className="accent-lime" />
          Starts only
        </label>
      </div>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="1+ SOT rate" value={formatPercent(one?.percentage)} detail={`${one?.successes ?? 0} of ${one?.valid ?? 0} valid starts${one?.missing ? ` · ${one.missing} missing` : ""}`} accent />
        <StatCard label="2+ SOT rate" value={formatPercent(two?.percentage)} detail={`${two?.successes ?? 0} of ${two?.valid ?? 0} valid starts`} />
        <StatCard label="Average SOT" value={formatNumber(metrics.average_sot_per_start)} detail={`${formatNumber(metrics.sot_per_90)} per 90 minutes`} />
        <StatCard label="Shot accuracy" value={formatPercent(metrics.shot_accuracy)} detail={`${metrics.total_shots_on_target} SOT from ${metrics.total_shots} shots`} />
      </section>

      <section className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <Panel title="SOT match trend" kicker="Recent starts">
          <SotTrendChart matches={matches.data.items} />
        </Panel>
        <Panel title="Home / away" kicker="Venue split">
          <div className="space-y-5">
            {(["home", "away"] as const).map((key) => {
              const rate = splits.data?.venue[key];
              return (
                <div key={key}>
                  <div className="mb-2 flex items-end justify-between">
                    <span className="text-sm capitalize text-slate-300">{key}</span>
                    <span className="text-xl font-semibold text-white tabular">{formatPercent(rate?.percentage)}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-white/[0.07]">
                    <div className="h-full rounded-full bg-lime" style={{ width: `${(rate?.percentage ?? 0) * 100}%` }} />
                  </div>
                  <p className="mt-2 text-xs text-slate-500">{rate?.successes ?? 0}/{rate?.valid ?? 0} valid starts</p>
                </div>
              );
            })}
            <div className="border-t border-white/10 pt-4 text-sm text-slate-400">
              Last zero-SOT start: <span className="text-slate-200">{streaks.data?.streak.last_failure_date ? formatMatchDate(streaks.data.streak.last_failure_date) : "Never in this sample"}</span>
            </div>
          </div>
        </Panel>
      </section>

      <Panel title="Match log" kicker={`${matches.data.pagination.total} matching appearances`}>
        <MatchTable matches={matches.data.items} />
        {matches.data.pagination.total_pages > 1 && (
          <div className="mt-5 flex justify-end gap-2">
            <button className="button-secondary" disabled={page <= 1} onClick={() => update("page", String(page - 1))}>Previous</button>
            <button className="button-secondary" disabled={page >= matches.data.pagination.total_pages} onClick={() => update("page", String(page + 1))}>Next</button>
          </div>
        )}
      </Panel>

      <section className="grid gap-6 md:grid-cols-2">
        <Panel title="Competition split" kicker="Sample-aware">
          <SplitList items={splits.data?.competitions ?? []} />
        </Panel>
        <Panel title="Opponent split" kicker="Historical matchups">
          <SplitList items={(splits.data?.opponents ?? []).slice(0, 8)} />
        </Panel>
      </section>
    </div>
  );
}

function FilterGroup({ label, values, active, onSelect, display = (value) => value }: { label: string; values: string[]; active: string; onSelect: (value: string) => void; display?: (value: string) => string }) {
  return (
    <div className="flex items-center gap-1">
      <span className="px-2 text-[10px] uppercase tracking-wider text-slate-600">{label}</span>
      {values.map((value) => (
        <button key={value} onClick={() => onSelect(value)} className={`rounded-xl px-3 py-2 text-xs capitalize transition ${active === value ? "bg-lime text-ink-950" : "text-slate-400 hover:bg-white/[0.05] hover:text-white"}`}>{display(value)}</button>
      ))}
    </div>
  );
}

function SplitList({ items }: { items: PlayerSplitsResponse["competitions"] }) {
  if (!items.length) return <p className="py-8 text-sm text-slate-500">No split data for this selection.</p>;
  return (
    <div className="space-y-1">
      {items.map((entry) => (
        <div key={String(entry.key)} className="flex items-center justify-between rounded-xl px-3 py-3 hover:bg-white/[0.03]">
          <span className="text-sm text-slate-300">{entry.label}</span>
          <span className="text-right"><span className="font-semibold text-white tabular">{formatPercent(entry.rate.percentage)}</span><span className="ml-2 text-xs text-slate-500">{entry.rate.successes}/{entry.rate.valid}</span></span>
        </div>
      ))}
    </div>
  );
}
