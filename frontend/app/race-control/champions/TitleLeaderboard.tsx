"use client";

import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Panel, rcFont } from "@/app/race-control/components/RaceControlPrimitives";

interface TitleEntry {
  name: string;
  titles: number;
}

interface TitleLeaderboardProps {
  title: string;
  entries: TitleEntry[];
  color: string;
}

function shortName(name: string): string {
  // f1db stores full legal names ("Lewis Carl Davidson Hamilton"); show first + last.
  const parts = name.trim().split(/\s+/);
  return parts.length > 1 ? `${parts[0]} ${parts[parts.length - 1]}` : name;
}

function LeaderboardTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: TitleEntry }>;
}) {
  if (!active || !payload?.length) return null;
  const entry = payload[0].payload;
  return (
    <div
      className="rounded-lg border px-3 py-2 text-sm shadow-xl"
      style={{ background: "#0F1210", borderColor: "rgba(255,255,255,0.12)" }}
    >
      <p className="font-black uppercase tracking-wider text-white" style={rcFont}>
        {shortName(entry.name)}
      </p>
      <p className="mt-0.5 font-mono text-neutral-300">
        {entry.titles} {entry.titles === 1 ? "title" : "titles"}
      </p>
    </div>
  );
}

export function TitleLeaderboard({ title, entries, color }: TitleLeaderboardProps) {
  const data = entries.slice(0, 10).map((e) => ({ ...e, label: shortName(e.name) }));
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
