"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";

import { ErrorState, LoadingState } from "@/components/LoadingState";
import { Panel } from "@/components/StatCard";
import { apiBaseUrl, apiGet } from "@/lib/api";
import { formatNumber, formatPercent } from "@/lib/utils";
import type { ComparisonResponse, TeamPlayersResponse, TeamRankingsResponse, TeamsResponse } from "@/types/api";

export default function ComparePage() {
  const [selected, setSelected] = useState<number[]>([]);
  // The teams endpoint places populated squads first so comparison always has
  // real candidates, even when the fixture feed contains opponent-only teams.
  const teams = useQuery({ queryKey: ["teams"], queryFn: () => apiGet<TeamsResponse>("/teams", { params: { page_size: 1 } }) });
  const teamId = teams.data?.items[0]?.id;
  const squad = useQuery({ queryKey: ["squad", teamId], queryFn: () => apiGet<TeamPlayersResponse>(`/teams/${teamId}/players`), enabled: Boolean(teamId) });
  const rankings = useQuery({
    queryKey: ["rankings", teamId, "comparison-defaults"],
    queryFn: () => apiGet<TeamRankingsResponse>(`/teams/${teamId}/sot-rankings`, { params: { minimum_starts: 1 } }),
    enabled: Boolean(teamId),
  });

  useEffect(() => {
    if (rankings.data && selected.length === 0) {
      setSelected(rankings.data.items.filter((entry) => entry.rate.valid > 0).slice(0, 2).map((entry) => entry.player.id));
    }
  }, [rankings.data, selected.length]);

  const comparison = useQuery({
    queryKey: ["comparison", selected],
    queryFn: async () => {
      const query = new URLSearchParams();
      selected.forEach((id) => query.append("player_ids", String(id)));
      const response = await fetch(`${apiBaseUrl()}/players/compare?${query}`);
      if (!response.ok) throw new Error("Comparison failed");
      return (await response.json()) as ComparisonResponse;
    },
    enabled: selected.length >= 2 && selected.length <= 4,
  });

  const toggle = (id: number) => setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : current.length < 4 ? [...current, id] : current);
  if (teams.isPending || squad.isPending || rankings.isPending) return <LoadingState />;
  if (teams.isError || squad.isError || rankings.isError) return <ErrorState />;

  return (
    <div className="space-y-6">
      <section className="panel"><p className="eyebrow">Side-by-side evidence</p><h1 className="mt-2 text-4xl font-semibold tracking-[-0.05em] text-white">Player comparison</h1><p className="mt-3 max-w-xl text-sm text-slate-400">Choose two to four players. Every percentage keeps its sample size attached.</p></section>
      <Panel title="Select players" kicker={`${selected.length}/4 selected`}>
        <div className="flex flex-wrap gap-2">{squad.data?.items.map((player) => { const active = selected.includes(player.id); return <button key={player.id} onClick={() => toggle(player.id)} className={active ? "button-primary" : "button-secondary"}>{active ? "✓ " : "+ "}{player.display_name}</button>; })}</div>
      </Panel>
      {selected.length < 2 ? <p className="panel text-sm text-slate-400">Select at least two players.</p> : comparison.isPending ? <LoadingState label="Comparing starts" /> : comparison.isError ? <ErrorState /> : (
        <Panel title="Comparison matrix" kicker="Competitive starts">
          <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm"><thead><tr className="border-b border-white/10 text-[10px] uppercase tracking-widest text-slate-500"><th className="p-3">Player</th><th>1+ SOT</th><th>2+ SOT</th><th>Avg SOT</th><th>SOT / 90</th><th>Home</th><th>Away</th><th>Last 5</th><th>Streak</th></tr></thead><tbody>{comparison.data?.items.map((entry) => <tr key={entry.player.id} className="border-b border-white/[0.06]"><td className="p-3"><Link href={`/players/${entry.player.id}`} className="font-medium text-white hover:text-lime">{entry.player.display_name}</Link><span className="block text-xs text-slate-500">{entry.valid_starts} valid starts</span></td><RateCell rate={entry.one_plus_rate} /><RateCell rate={entry.two_plus_rate} /><td className="text-slate-300">{formatNumber(entry.average_sot)}</td><td className="text-slate-300">{formatNumber(entry.sot_per_90)}</td><RateCell rate={entry.home_rate} /><RateCell rate={entry.away_rate} /><RateCell rate={entry.last_five_rate} /><td className="font-semibold text-lime">{entry.current_streak}</td></tr>)}</tbody></table></div>
        </Panel>
      )}
    </div>
  );
}

function RateCell({ rate }: { rate: { percentage: number | null; successes: number; valid: number } }) {
  return <td className="text-slate-300 tabular"><span className="font-semibold text-white">{formatPercent(rate.percentage)}</span><span className="block text-[10px] text-slate-500">{rate.successes}/{rate.valid}</span></td>;
}
