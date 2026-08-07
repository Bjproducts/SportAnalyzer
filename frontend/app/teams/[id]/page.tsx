"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { ErrorState, LoadingState } from "@/components/LoadingState";
import { Panel } from "@/components/StatCard";
import { apiGet } from "@/lib/api";
import { formatNumber, formatPercent } from "@/lib/utils";
import type { TeamRankingsResponse, Venue } from "@/types/api";

export default function TeamPage() {
  const id = Number(useParams<{ id: string }>().id);
  const [venue, setVenue] = useState<Venue>("all");
  const [minimum, setMinimum] = useState(5);
  const [window, setWindow] = useState<5 | 10 | 20>(5);
  const result = useQuery({ queryKey: ["team-rankings", id, venue, minimum, window], queryFn: ({ signal }) => apiGet<TeamRankingsResponse>(`/teams/${id}/sot-rankings`, { params: { venue, minimum_starts: minimum, last_n: window, limit: 5 }, signal }) });
  if (result.isPending) return <LoadingState label="Ranking squad" />;
  if (result.isError || !result.data) return <ErrorState />;
  return (
    <div className="space-y-6">
      <section className="panel flex flex-col justify-between gap-6 md:flex-row md:items-end"><div><p className="eyebrow">Squad analytics</p><h1 className="mt-2 text-4xl font-semibold tracking-[-0.05em] text-white">{result.data.team.name}</h1><p className="mt-2 text-sm text-slate-400">Ranked with sample-adjusted rates—not percentage alone.</p></div><Link href="/compare" className="button-primary">Compare squad</Link></section>
      <div className="flex flex-wrap items-center gap-2">{(["all", "home", "away"] as Venue[]).map((value) => <button key={value} onClick={() => setVenue(value)} className={venue === value ? "button-primary capitalize" : "button-secondary capitalize"}>{value}</button>)}<span className="mx-1 h-7 w-px bg-white/10" />{([5, 10, 20] as const).map((value) => <button key={value} onClick={() => setWindow(value)} className={window === value ? "button-primary" : "button-secondary"}>Last {value}</button>)}<label className="ml-auto text-xs text-slate-400">Minimum starts <select value={minimum} onChange={(e) => setMinimum(Number(e.target.value))} className="ml-2 rounded-lg border border-white/10 bg-ink-800 px-2 py-2 text-white"><option>1</option><option>3</option><option>5</option><option>10</option></select></label></div>
      <Panel title="Top 5 SOT candidates" kicker={`${venue} · last ${window} across all competitions · minimum ${minimum} starts`}>
        <div className="overflow-x-auto"><table className="w-full min-w-[720px] text-left text-sm"><thead><tr className="border-b border-white/10 text-[10px] uppercase tracking-widest text-slate-500"><th className="p-3">Rank</th><th>Player</th><th>Hit rate</th><th>Last 5</th><th>Avg SOT</th><th>Streak</th><th>Evidence</th></tr></thead><tbody>{result.data.items.map((entry) => <tr key={entry.player.id} className="border-b border-white/[0.06]"><td className="p-3 font-mono text-slate-600">{String(entry.rank).padStart(2, "0")}</td><td><Link className="font-medium text-white hover:text-lime" href={`/players/${entry.player.id}`}>{entry.player.display_name}</Link><span className="block text-xs text-slate-500">{entry.player.primary_position}</span></td><td className="font-semibold text-white tabular">{formatPercent(entry.rate.percentage)} <span className="block text-xs font-normal text-slate-500">{entry.rate.successes}/{entry.rate.valid}</span></td><td className="text-slate-300 tabular">{formatPercent(entry.last_five_rate)}</td><td className="text-slate-300 tabular">{formatNumber(entry.average_sot)}</td><td className="text-slate-300 tabular">{entry.current_streak}</td><td>{entry.eligible ? <span className="tag">Eligible</span> : <span className="rounded-full bg-amber-300/10 px-2 py-1 text-[10px] text-amber-300">Small sample</span>}</td></tr>)}</tbody></table></div>
      </Panel>
    </div>
  );
}
