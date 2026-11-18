"use client";

import { useId } from "react";

import { AnimatedNumber } from "@/app/ui/AnimatedNumber";
import { driverLabel } from "@/app/ui/names/names";
import { RetryButton, StaleMark } from "@/app/ui/section/Section";
import type { SectionState } from "@/app/ui/section/sectionState";
import { StatTile, StatTiles } from "@/app/ui/StatTile";

import { WeatherGlyph } from "./WeatherGlyph";
import { formatPoints } from "./weekendModel";

import type { CircuitRecord, SessionForecast, TableStakes } from "./weekendTypes";
import type { ReactNode } from "react";

interface TileProps {
  label: string;
  /** The state of the segment the tile is read from (`useSection`). */
  state: SectionState;
  value: ReactNode;
  unit?: string;
  sub: string;
  visual?: ReactNode;
  index: number;
}

/**
 * A tile's figure and caption for its segment's state. Data stays on screen
 * whenever there is some (ready or stale); "Unavailable" and the reason show
 * only when the segment has none, and nothing is captioned before it loads.
 */
function shownFor(
  state: SectionState,
  value: ReactNode,
  unit: string | undefined,
  sub: string,
): { figure: ReactNode; unit: string | undefined; caption: string | null } {
  if (state.status === "pending") return { figure: "…", unit: undefined, caption: null };
  if (state.status === "failed") {
    return {
      figure: <span className="text-base text-rc-ink-3">Unavailable</span>,
      unit: undefined,
      caption: state.reason,
    };
  }
  return { figure: value, unit, caption: sub };
}

function Tile({ label, state, value, unit, sub, visual, index }: TileProps) {
  const labelId = useId();
  const shown = shownFor(state, value, unit, sub);
  const hasData = state.status === "ready" || state.status === "stale";
  return (
    <div
      role="group"
      aria-labelledby={labelId}
      className="flex min-w-0 items-start justify-between gap-3 motion-safe:animate-fade-up"
      style={{ animationDelay: `${index * 0.07}s` }}
    >
      <div className="min-w-0">
        <StatTile
          labelId={labelId}
          label={label}
          value={shown.figure}
          unit={shown.unit}
          sub={shown.caption ?? undefined}
        />
        {state.status === "stale" && <StaleMark state={state} className="mt-2" />}
        {state.status === "failed" && (
          <p className="mt-2">
            <RetryButton state={state} />
          </p>
        )}
      </div>
      {hasData && visual}
    </div>
  );
}

export interface KeyNumbersProps {
  rain: { value: number | null; source: string; forecast: SessionForecast | null; state: SectionState };
  /** The latest same-circuit edition's median pit-lane time (`pitLaneFigure`). */
  pit: { seconds: number | null; detail: string; state: SectionState };
  title: { stakes: TableStakes | null | undefined; state: SectionState };
  history: { record: CircuitRecord | null | undefined; state: SectionState };
}

function titleTile(stakes: TableStakes | null | undefined): { value: ReactNode; unit?: string; sub: string } {
  if (!stakes) return { value: "—", sub: "Standings unavailable" };
  const rival = stakes.contenders[1];
  const leader = driverLabel(stakes.leader, "full");
  if (stakes.decided) return { value: "Decided", sub: `${leader} has clinched the title` };
  if (!rival) return { value: "—", sub: `${leader} leads unopposed` };
  return {
    value: <AnimatedNumber value={rival.gap} />,
    unit: "pts",
    sub: `${leader} leads ${driverLabel(rival, "full")} · ${formatPoints(stakes.max_available)} still on offer`,
  };
}

function poleTile(record: CircuitRecord | null | undefined): { value: ReactNode; unit?: string; sub: string } {
  const conversion = record?.pole_conversion;
  if (!conversion || conversion.editions === 0) return { value: "—", sub: "No earlier race at this circuit" };
  return {
    value: conversion.wins_from_pole,
    unit: `/${conversion.editions}`,
    sub: `Poles converted to wins in the last ${conversion.editions} races here`,
  };
}

export function KeyNumbers({ rain, pit, title, history }: KeyNumbersProps) {
  const titleValue = titleTile(title.stakes);
  const poleValue = poleTile(history.record);
  return (
    <StatTiles className="w-full">
      <Tile
        index={0}
        label="Race-day rain"
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
          rain.forecast && <WeatherGlyph condition={rain.forecast.condition} isDay={rain.forecast.is_day} size={40} />
        }
      />
      <Tile
        index={1}
        label="Pit lane time"
        state={pit.state}
        value={
          pit.seconds === null ? (
            "—"
          ) : (
            <>
              <AnimatedNumber value={pit.seconds} decimals={1} />s
            </>
          )
        }
        sub={pit.detail}
      />
      <Tile
        index={2}
        label="Title gap"
        state={title.state}
        value={titleValue.value}
        unit={titleValue.unit}
        sub={titleValue.sub}
      />
      <Tile
        index={3}
        label="Pole → win here"
        state={history.state}
        value={poleValue.value}
        unit={poleValue.unit}
        sub={poleValue.sub}
      />
    </StatTiles>
  );
}
