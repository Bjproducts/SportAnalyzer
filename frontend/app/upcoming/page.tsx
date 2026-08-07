"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { ErrorState, LoadingState } from "@/components/LoadingState";
import { apiGet } from "@/lib/api";
import { formatNumber, formatPercent } from "@/lib/utils";
import type {
  DailyFixtureAnalysisResponse,
  FixtureCandidate,
  FixturePreview,
  TeamFixturePreview,
} from "@/types/api";

const todayUtc = () => new Date().toISOString().slice(0, 10);

function shiftDate(value: string, days: number): string {
  const current = new Date(`${value}T12:00:00Z`);
  current.setUTCDate(current.getUTCDate() + days);
  return current.toISOString().slice(0, 10);
}

function kickoff(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(value));
}

export default function UpcomingPage() {
  const [date, setDate] = useState(todayUtc);
  const [window, setWindow] = useState<5 | 10 | 20>(5);
  const result = useQuery({
    queryKey: ["upcoming-analysis", date, window],
    queryFn: ({ signal }) =>
      apiGet<DailyFixtureAnalysisResponse>("/fixtures/upcoming-analysis", {
        params: { date, window, candidates_per_team: 5 },
        signal,
      }),
  });

  return (
    <div className="space-y-6">
      <section className="panel overflow-hidden">
        <div className="grid gap-7 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <p className="eyebrow">Daily matchup lab</p>
            <h1 className="mt-2 max-w-3xl text-4xl font-semibold tracking-[-0.05em] text-white md:text-5xl">
              Upcoming fixtures. Ranked with context.
            </h1>
            <p className="mt-4 max-w-2xl text-sm leading-6 text-slate-400">
              Five SOT candidates per team, adjusted for recent form, venue, minutes,
              sample reliability and the opponent&apos;s defensive record.
            </p>
          </div>
          <div className="rounded-2xl border border-lime/20 bg-lime/[0.05] p-4 text-xs leading-5 text-slate-400 lg:max-w-xs">
            <span className="font-semibold text-lime">Research score, not probability.</span>{" "}
            Lineups and tactical roles remain unconfirmed until matchday.
          </div>
        </div>
      </section>

      <section className="panel flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <label htmlFor="fixture-date" className="eyebrow">Fixture date (UTC)</label>
          <div className="mt-2 flex items-center gap-2">
            <button className="button-secondary" onClick={() => setDate((value) => shiftDate(value, -1))} aria-label="Previous day">←</button>
            <input
              id="fixture-date"
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
              className="rounded-xl border border-white/10 bg-ink-800 px-3 py-2 text-sm text-white [color-scheme:dark]"
            />
            <button className="button-secondary" onClick={() => setDate((value) => shiftDate(value, 1))} aria-label="Next day">→</button>
            <button className="button-secondary" onClick={() => setDate(todayUtc())}>Today</button>
          </div>
        </div>
        <div>
          <p className="eyebrow">Evidence window</p>
          <div className="mt-2 flex gap-2">
            {([5, 10, 20] as const).map((value) => (
              <button key={value} onClick={() => setWindow(value)} className={window === value ? "button-primary" : "button-secondary"}>
                Last {value}
              </button>
            ))}
          </div>
        </div>
      </section>

      {result.isPending ? (
        <LoadingState label="Analyzing the matchups" />
      ) : result.isError || !result.data ? (
        <ErrorState />
      ) : result.data.fixtures.length === 0 ? (
        <EmptyDay date={date} onNext={() => setDate((value) => shiftDate(value, 1))} />
      ) : (
        <>
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="eyebrow">{result.data.fixtures.length} scheduled {result.data.fixtures.length === 1 ? "fixture" : "fixtures"}</p>
              <h2 className="mt-1 text-xl font-semibold text-white">Best candidates for {date}</h2>
            </div>
            <span className="tag">Last {window} starts</span>
          </div>
          {result.data.fixtures.map((preview) => <FixtureCard key={preview.fixture.id} preview={preview} />)}
          <section className="rounded-2xl border border-white/[0.07] bg-white/[0.025] p-4 text-xs leading-5 text-slate-500">
            <p>{result.data.methodology}</p>
            <p className="mt-2 text-amber-200/70">{result.data.disclaimer}</p>
          </section>
        </>
      )}
    </div>
  );
}

function EmptyDay({ date, onNext }: { date: string; onNext: () => void }) {
  return (
    <section className="panel py-14 text-center">
      <p className="eyebrow">No scheduled fixtures</p>
      <h2 className="mt-2 text-2xl font-semibold text-white">Nothing stored for {date}</h2>
      <p className="mx-auto mt-3 max-w-lg text-sm text-slate-400">
        Pick another date. This screen uses the fixtures already in your database and does not spend an API call.
      </p>
      <button className="button-primary mt-6" onClick={onNext}>Check next day →</button>
    </section>
  );
}

function FixtureCard({ preview }: { preview: FixturePreview }) {
  const { fixture } = preview;
  return (
    <article className="panel space-y-5">
      <header className="flex flex-col justify-between gap-4 border-b border-white/[0.07] pb-5 sm:flex-row sm:items-center">
        <div>
          <p className="eyebrow">{fixture.competition.name} · {fixture.round ?? fixture.season.label}</p>
          <h2 className="mt-2 text-xl font-semibold text-white">
            {fixture.home_team.name} <span className="px-1 text-slate-600">vs</span> {fixture.away_team.name}
          </h2>
        </div>
        <div className="text-left sm:text-right">
          <p className="font-mono text-sm font-semibold text-lime">{kickoff(fixture.fixture_date)}</p>
          <p className="mt-1 text-xs text-slate-500">{fixture.venue ?? "Venue not reported"}</p>
        </div>
      </header>
      <div className="grid gap-5 xl:grid-cols-2">
        <TeamCandidates preview={preview.home} />
        <TeamCandidates preview={preview.away} />
      </div>
    </article>
  );
}

function TeamCandidates({ preview }: { preview: TeamFixturePreview }) {
  const defenseTone = preview.opponent_defense.label === "strong"
    ? "text-amber-300"
    : preview.opponent_defense.label === "vulnerable"
      ? "text-lime"
      : "text-slate-400";

  return (
    <section className="rounded-2xl border border-white/[0.07] bg-ink-950/45 p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="eyebrow">{preview.venue} candidates</p>
          <Link href={`/teams/${preview.team.id}`} className="mt-1 block text-lg font-semibold text-white hover:text-lime">
            {preview.team.name}
          </Link>
        </div>
        <div className="max-w-[15rem] text-right text-[11px] leading-4">
          <p className={defenseTone}>{preview.opponent_defense.description}</p>
          <p className="mt-1 text-slate-600">{preview.opponent_defense.matches} match sample</p>
        </div>
      </div>
      {preview.warning ? (
        <p className="mt-4 rounded-xl border border-amber-300/15 bg-amber-300/[0.05] p-3 text-xs text-amber-200">{preview.warning}</p>
      ) : null}
      <ol className="mt-4 space-y-3">
        {preview.candidates.map((candidate) => <CandidateCard key={candidate.player.id} candidate={candidate} />)}
      </ol>
    </section>
  );
}

function CandidateCard({ candidate }: { candidate: FixtureCandidate }) {
  const scoreTone = candidate.score_label === "strong"
    ? "border-lime/25 bg-lime/[0.06] text-lime"
    : candidate.score_label === "viable"
      ? "border-sky-300/20 bg-sky-300/[0.05] text-sky-300"
      : "border-white/10 bg-white/[0.03] text-slate-400";

  return (
    <li className="rounded-xl border border-white/[0.07] bg-white/[0.018] p-3">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 font-mono text-xs text-slate-600">{String(candidate.rank).padStart(2, "0")}</span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <Link href={`/players/${candidate.player.id}`} className="font-semibold text-white hover:text-lime">
                {candidate.player.display_name}
              </Link>
              <p className="mt-0.5 text-[11px] text-slate-500">{candidate.player.primary_position ?? candidate.player.position_group}</p>
            </div>
            <span className={`rounded-lg border px-2 py-1 font-mono text-sm font-bold ${scoreTone}`} title="Research score, not a probability">
              {candidate.research_score}
            </span>
          </div>
          <div className="mt-3 grid grid-cols-4 gap-2 text-[11px]">
            <Metric label="1+ SOT" value={`${formatPercent(candidate.recent_rate.percentage)} · ${candidate.recent_rate.successes}/${candidate.recent_rate.valid}`} />
            <Metric label="Venue" value={`${formatPercent(candidate.venue_rate.percentage)} · ${candidate.venue_rate.valid}`} />
            <Metric label="Avg SOT" value={formatNumber(candidate.average_sot)} />
            <Metric label="Avg min" value={candidate.average_minutes === null ? "—" : candidate.average_minutes.toFixed(0)} />
          </div>
          <details className="mt-3 text-xs">
            <summary className="cursor-pointer select-none text-slate-400 hover:text-white">Why this rank · risks</summary>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div>
                <p className="eyebrow text-lime">Evidence</p>
                <ul className="mt-1 space-y-1 text-slate-400">{candidate.reasons.map((reason) => <li key={reason}>+ {reason}</li>)}</ul>
              </div>
              <div>
                <p className="eyebrow text-amber-300">Failure risks</p>
                <ul className="mt-1 space-y-1 text-slate-400">{candidate.risks.map((risk) => <li key={risk}>− {risk}</li>)}</ul>
              </div>
            </div>
          </details>
        </div>
      </div>
    </li>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[9px] uppercase tracking-wider text-slate-600">{label}</p>
      <p className="mt-0.5 truncate font-mono text-slate-300" title={value}>{value}</p>
    </div>
  );
}
