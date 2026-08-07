"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { ApiStatus } from "@/components/ApiStatus";
import { ErrorState, LoadingState } from "@/components/LoadingState";
import { PlayerSearch } from "@/components/PlayerSearch";
import { Panel } from "@/components/StatCard";
import { apiGet } from "@/lib/api";
import { formatNumber, formatPercent } from "@/lib/utils";
import type { TeamRankingsResponse, TeamsResponse } from "@/types/api";

export default function DashboardPage() {
  const teams = useQuery({ queryKey: ["teams"], queryFn: ({ signal }) => apiGet<TeamsResponse>("/teams", { params: { page_size: 6 }, signal }) });
  const featuredTeam = teams.data?.items[0];
  const leaders = useQuery({
    queryKey: ["rankings", featuredTeam?.id],
    queryFn: ({ signal }) => apiGet<TeamRankingsResponse>(`/teams/${featuredTeam!.id}/sot-rankings`, { params: { minimum_starts: 5, last_n: 5, limit: 5 }, signal }),
    enabled: Boolean(featuredTeam),
  });

  return (
    <div className="space-y-8">
      <section className="hero-grid relative overflow-hidden rounded-[2rem] border border-white/10 bg-ink-800 px-6 py-12 md:px-12 md:py-16">
        <div className="absolute -right-24 -top-36 h-96 w-96 rounded-full bg-lime/10 blur-3xl" />
        <div className="relative max-w-3xl">
          <div className="mb-8 flex items-center gap-3"><span className="tag">Match intelligence</span><ApiStatus /></div>
          <p className="eyebrow text-lime">Evidence over instinct</p>
          <h1 className="mt-3 text-5xl font-semibold leading-[0.95] tracking-[-0.06em] text-white md:text-7xl">Know who tests<br />the goalkeeper.</h1>
          <p className="mt-6 max-w-2xl text-base leading-7 text-slate-400">Search every appearance. Separate home from away. Track SOT form, misses and streaks without turning missing data into a made-up zero.</p>
          <div className="mt-8 max-w-2xl"><PlayerSearch /></div>
          <p className="mt-4 text-xs text-slate-600">Authorized provider data · auditable imports · sample-aware results</p>
        </div>
      </section>

      {teams.isPending ? <LoadingState label="Loading competitions" /> : teams.isError ? <ErrorState /> : (
        <section className="grid gap-6 lg:grid-cols-[1.55fr_1fr]">
          <Panel title="Top 5 SOT candidates" kicker={`${featuredTeam?.name ?? "Current team"} · last 5`}>
            {leaders.isPending ? <LoadingState /> : (
              <div className="space-y-1">
                {leaders.data?.items.slice(0, 5).map((entry) => (
                  <Link href={`/players/${entry.player.id}`} key={entry.player.id} className="grid grid-cols-[2rem_1fr_auto_auto] items-center gap-3 rounded-xl px-3 py-3 transition hover:bg-white/[0.04]">
                    <span className="font-mono text-xs text-slate-600">{String(entry.rank).padStart(2, "0")}</span>
                    <span><span className="block text-sm font-medium text-white">{entry.player.display_name}</span><span className="text-xs text-slate-500">{entry.player.primary_position}</span></span>
                    <span className="text-right"><span className="block font-semibold text-white tabular">{formatPercent(entry.rate.percentage)}</span><span className="text-[10px] text-slate-500">{entry.rate.successes}/{entry.rate.valid} starts</span></span>
                    <span className="hidden w-16 text-right text-xs text-slate-400 sm:block">{formatNumber(entry.average_sot)} avg</span>
                  </Link>
                ))}
              </div>
            )}
            {featuredTeam && <Link href={`/teams/${featuredTeam.id}`} className="button-secondary mt-5 inline-flex">View full squad →</Link>}
          </Panel>
          <Panel title="Research workflow" kicker="Built for clarity">
            <ol className="space-y-5">
              {["Find a player", "Choose venue + window", "Read every start", "Compare the evidence"].map((step, index) => (
                <li key={step} className="flex items-center gap-4"><span className="grid h-8 w-8 place-items-center rounded-full border border-lime/20 bg-lime/[0.05] font-mono text-xs text-lime">{index + 1}</span><span className="text-sm text-slate-300">{step}</span></li>
              ))}
            </ol>
            <Link href="/compare" className="button-primary mt-7 inline-flex">Compare players</Link>
          </Panel>
        </section>
      )}
    </div>
  );
}
