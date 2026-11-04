"use client";

import { CloudRain, Crown, Target, Timer } from "lucide-react";

import { AnimatedNumber } from "@/app/ui/AnimatedNumber";
import { driverLabel } from "@/app/ui/names/names";

import { WeatherGlyph } from "./WeatherGlyph";
import { formatPoints, rainColor } from "./weekendModel";

import type { CircuitRecord, SessionForecast, TableStakes } from "./weekendTypes";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** Where a tile's segment stands: still loading, failed, or ready. */
export type TileState = "pending" | "failed" | "ready";

interface TileProps {
  label: string;
  accent: string;
  icon: LucideIcon;
  state: TileState;
  value: ReactNode;
  sub: string;
  visual?: ReactNode;
  index: number;
}

function Tile({ label, accent, icon: Icon, state, value, sub, visual, index }: TileProps) {
  let shown: ReactNode = value;
  if (state === "pending") shown = "…";
  if (state === "failed") shown = <span className="text-base text-[#7F8797]">Unavailable</span>;
  return (
    <div
      className="relative min-w-0 overflow-hidden rounded-md border border-[#1E2633] bg-[#0D111B] p-4 motion-safe:animate-fade-up"
      style={{ animationDelay: `${index * 0.07}s` }}
    >
      <div className="absolute inset-x-0 top-0 h-[2px]" style={{ background: accent }} />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-[#7F8797]">
            <Icon className="h-3.5 w-3.5" style={{ color: accent }} aria-hidden="true" />
            {label}
          </p>
          <p className="mt-2 font-mono text-3xl font-black leading-tight text-white">{shown}</p>
        </div>
        {state === "ready" && visual}
      </div>
      <p className="mt-1 line-clamp-2 text-xs leading-snug text-[#6F7789]">{sub}</p>
    </div>
  );
}

export interface KeyNumbersProps {
  rain: { value: number | null; source: string; forecast: SessionForecast | null; state: TileState };
  pit: { lossSeconds: number | null; detail: string; state: TileState };
  title: { stakes: TableStakes | null | undefined; state: TileState };
  history: { record: CircuitRecord | null | undefined; state: TileState };
}

function titleTile(stakes: TableStakes | null | undefined): { value: ReactNode; sub: string } {
  if (!stakes) return { value: "—", sub: "Standings unavailable" };
  const rival = stakes.contenders[1];
  const leader = driverLabel(stakes.leader, "full");
  if (stakes.decided) return { value: "Decided", sub: `${leader} has clinched the title` };
  if (!rival) return { value: "—", sub: `${leader} leads unopposed` };
  return {
    value: (
      <>
        <AnimatedNumber value={rival.gap} />
        <span className="ml-1 text-base text-[#8E96A8]">pts</span>
      </>
    ),
    sub: `${leader} leads ${driverLabel(rival, "full")} · ${formatPoints(stakes.max_available)} still on offer`,
  };
}

function poleTile(record: CircuitRecord | null | undefined): { value: ReactNode; sub: string } {
  const conversion = record?.pole_conversion;
  if (!conversion || conversion.editions === 0) return { value: "—", sub: "No earlier race at this circuit" };
  return {
    value: (
      <>
        {conversion.wins_from_pole}
        <span className="text-lg text-[#6F7789]">/{conversion.editions}</span>
      </>
    ),
    sub: `Poles converted to wins in the last ${conversion.editions} races here`,
  };
}

export function KeyNumbers({ rain, pit, title, history }: KeyNumbersProps) {
  const titleValue = titleTile(title.stakes);
  const poleValue = poleTile(history.record);
  return (
    <div className="mb-5 grid w-full min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Tile
        index={0}
        label="Race-day rain"
        accent={rainColor(rain.value)}
        icon={CloudRain}
        state={rain.state}
        value={
          rain.value === null ? (
            "—"
          ) : (
            <>
              <AnimatedNumber value={rain.value} />%
            </>
          )
        }
        sub={rain.source}
        visual={
          rain.forecast && <WeatherGlyph condition={rain.forecast.condition} isDay={rain.forecast.is_day} size={44} />
        }
      />
      <Tile
        index={1}
        label="Pit lane loss"
        accent="#3671C6"
        icon={Timer}
        state={pit.state}
        value={
          pit.lossSeconds === null ? (
            "No model"
          ) : (
            <>
              <AnimatedNumber value={pit.lossSeconds} decimals={1} />s
            </>
          )
        }
        sub={pit.detail}
      />
      <Tile
        index={2}
        label="Title gap"
        accent="#FFC93C"
        icon={Crown}
        state={title.state}
        value={titleValue.value}
        sub={titleValue.sub}
      />
      <Tile
        index={3}
        label="Pole → win here"
        accent="#00FF78"
        icon={Target}
        state={history.state}
        value={poleValue.value}
        sub={poleValue.sub}
      />
    </div>
  );
}
