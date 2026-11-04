"use client";

import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { TitleEntry } from "@/app/lib/server/champions";
import { Panel, rcFont } from "@/app/race-control/components/RaceControlPrimitives";
import { driverLabel } from "@/app/ui/names/names";

interface TitleLeaderboardProps {
  title: string;
  entries: TitleEntry[];
  color: string;
}

/** f1db's surname on a driver row ("Fangio"); a constructor row has none and keeps its name. */
function axisLabel(entry: TitleEntry): string {
  return driverLabel({ name: entry.name, lastName: entry.last_name }, "last");
}

function LeaderboardTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: TitleEntry }> }) {
  if (!active || !payload?.length) return null;
  const entry = payload[0].payload;
  return (
    <div
      className="rounded-lg border px-3 py-2 text-sm shadow-xl"
      style={{ background: "#0F1210", borderColor: "rgba(255,255,255,0.12)" }}
    >
      <p className="font-black uppercase tracking-wider text-white" style={rcFont}>
        {entry.name}
      </p>
      <p className="mt-0.5 font-mono text-neutral-300">
        {entry.titles} {entry.titles === 1 ? "title" : "titles"}
      </p>
    </div>
  );
}

export function TitleLeaderboard({ title, entries, color }: TitleLeaderboardProps) {
  const data = entries.slice(0, 10).map((e) => ({ ...e, label: axisLabel(e) }));
  const max = data.length ? Math.max(...data.map((d) => d.titles)) : 1;

  return (
    <Panel className="p-4">
      <p className="mb-3 text-[11px] font-bold uppercase tracking-[0.22em] text-[#7F8797]" style={rcFont}>
        {title}
      </p>
      <ResponsiveContainer width="100%" height={Math.max(220, data.length * 28)}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 20, bottom: 0, left: 8 }}>
          <XAxis type="number" domain={[0, max]} hide />
          <YAxis
            type="category"
            dataKey="label"
            width={120}
            tick={{ fill: "#d4d4d4", fontSize: 11, fontWeight: 700 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<LeaderboardTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
          <Bar dataKey="titles" radius={[0, 4, 4, 0]} maxBarSize={18}>
            {data.map((entry) => (
              <Cell key={entry.name} fill={color} fillOpacity={0.85} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Panel>
  );
}
