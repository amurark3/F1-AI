"use client";

import { useState } from "react";
import useSWR from "swr";

import { API_BASE } from "@/app/constants/api";
import { fetcher } from "@/app/utils/fetcher";

import { Disclosure } from "../../components/Disclosure";
import { StatusPill } from "../../components/RaceControlPrimitives";

/** `GET /api/race-control/intel/{slug}` — gap-based reads from the standings. */
interface Intel {
  team?: { name: string; color: string; strategy_tendency: string; strengths: string[]; weaknesses: string[] };
  status?: string;
  upgrade_watch: string[];
  threats: string[];
  opportunities: string[];
  error?: string | null;
}

function Items({ title, items, tone }: { title: string; items: string[]; tone: "neutral" | "threat" | "chance" }) {
  if (items.length === 0) return null;
  const style = {
    neutral: "border-white/6 bg-white/[0.025]",
    threat: "border-red-500/20 bg-red-500/[0.035]",
    chance: "border-[#00FF78]/20 bg-[#00FF78]/[0.035]",
  }[tone];
  return (
    <div>
      <p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-[#6F7789]">{title}</p>
      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item} className={`rounded-md border p-3 text-sm text-neutral-300 ${style}`}>
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function IntelBody({ data, color }: { data: Intel; color: string }) {
  if (data.error || data.status !== "ok" || !data.team) {
    return <p className="text-sm text-[#8E96A8]">The championship read is not available right now.</p>;
  }
  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed text-neutral-400">{data.team.strategy_tendency}</p>
      <div className="flex flex-wrap gap-2">
        {data.team.strengths.map((item) => (
          <StatusPill key={item} color={color}>
            {item}
          </StatusPill>
        ))}
        {data.team.weaknesses.map((item) => (
          <StatusPill key={item} color="#FFF200">
            {item}
          </StatusPill>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Items title="Evidence" items={data.upgrade_watch} tone="neutral" />
        <Items title="Threats" items={data.threats} tone="threat" />
        <Items title="Opportunities" items={data.opportunities} tone="chance" />
      </div>
    </div>
  );
}

/**
 * The standings-derived threats and opportunities, collapsed by default and
 * fetched only when opened — they are a secondary read on the same table the
 * page already shows.
 */
export function ChampionshipPicture({ slug, color }: { slug: string; color: string }) {
  const [opened, setOpened] = useState(false);
  const { data, error, isLoading } = useSWR<Intel, Error>(
    opened ? `${API_BASE}/api/race-control/intel/${encodeURIComponent(slug)}` : null,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 180000 },
  );

  return (
    <Disclosure
      title="Championship picture"
      hint="Gaps to the teams around them"
      onOpenChange={(open) => open && setOpened(true)}
      className="mb-5"
    >
      {isLoading && <p className="text-sm text-[#8E96A8]">Reading the constructor table…</p>}
      {error && <p className="text-sm text-[#FFB4B1]">The championship read could not be loaded.</p>}
      {data && <IntelBody data={data} color={color} />}
    </Disclosure>
  );
}
