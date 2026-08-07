"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatMatchDate } from "@/lib/utils";
import type { PlayerMatch } from "@/types/api";

export function SotTrendChart({ matches }: { matches: PlayerMatch[] }) {
  const data = [...matches]
    .reverse()
    .map((match) => ({ date: formatMatchDate(match.fixture_date), sot: match.shots_on_target }));

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -24 }}>
          <CartesianGrid stroke="rgba(255,255,255,.06)" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={28} />
          <YAxis allowDecimals={false} tick={{ fill: "#64748b", fontSize: 10 }} tickLine={false} axisLine={false} />
          <Tooltip
            contentStyle={{ background: "#101827", border: "1px solid rgba(255,255,255,.1)", borderRadius: 12 }}
            labelStyle={{ color: "#94a3b8" }}
          />
          <Line type="monotone" dataKey="sot" stroke="#b8f34a" strokeWidth={2.5} dot={{ r: 3, fill: "#b8f34a", strokeWidth: 0 }} connectNulls={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
