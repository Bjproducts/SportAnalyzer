"use client";

import { createColumnHelper, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";

import { formatInt, formatMatchDate } from "@/lib/utils";
import type { PlayerMatch } from "@/types/api";

import { OutcomeBadge } from "./OutcomeBadge";

const column = createColumnHelper<PlayerMatch>();

const columns = [
  column.accessor("fixture_date", {
    header: "Date",
    cell: (info) => <span className="whitespace-nowrap text-slate-300">{formatMatchDate(info.getValue())}</span>,
  }),
  column.accessor("opponent.name", {
    header: "Opponent",
    cell: (info) => <span className="font-medium text-white">{info.getValue()}</span>,
  }),
  column.accessor("venue", {
    header: "Venue",
    cell: (info) => <span className="uppercase text-slate-400">{info.getValue().slice(0, 1)}</span>,
  }),
  column.accessor("started", {
    header: "Role",
    cell: (info) => (info.getValue() ? "Start" : "Sub"),
  }),
  column.accessor("minutes_played", { header: "Min", cell: (info) => formatInt(info.getValue()) }),
  column.accessor("shots", { header: "Shots", cell: (info) => formatInt(info.getValue()) }),
  column.accessor("shots_on_target", {
    header: "SOT",
    cell: (info) => <span className="font-semibold text-white">{formatInt(info.getValue())}</span>,
  }),
  column.accessor("one_plus_sot", {
    header: "1+ SOT",
    cell: (info) => <OutcomeBadge value={info.getValue()} />,
  }),
  column.accessor("competition.name", { header: "Competition", cell: (info) => info.getValue() }),
];

export function MatchTable({ matches }: { matches: PlayerMatch[] }) {
  const table = useReactTable({ data: matches, columns, getCoreRowModel: getCoreRowModel() });

  if (matches.length === 0) {
    return <p className="py-12 text-center text-sm text-slate-400">No matches fit these filters.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[840px] border-collapse text-left text-sm">
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id} className="border-b border-white/10 text-[11px] uppercase tracking-[0.12em] text-slate-500">
              {group.headers.map((header) => (
                <th key={header.id} className="px-3 py-3 font-medium">
                  {flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} className="border-b border-white/[0.06] transition hover:bg-white/[0.025]">
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-3 py-3.5 text-slate-400 tabular">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
