import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useReducedMotion } from "framer-motion";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SectionState, SectionStatus } from "@/app/ui/section/sectionState";
import { CIRCUIT_RECORDS, SAO_PAULO_2026, SESSION_WEATHER_2026, STAKES_2026, STRATEGY_2026 } from "@/test/fixtures";

import { KeyNumbers, type KeyNumbersProps } from "./KeyNumbers";
import { pitLaneFigure } from "./pitLaneFigure";

import type * as FramerMotion from "framer-motion";

vi.mock("framer-motion", async (importOriginal) => ({
  ...(await importOriginal<typeof FramerMotion>()),
  useReducedMotion: vi.fn(),
}));

const { weatherCard, weather, strategy, stakes, circuit } = SAO_PAULO_2026;

/** A segment's state as `useSection` reports it. */
function section(status: SectionStatus = "ready", reason: string | null = null): SectionState {
  return { status, reason, refreshing: false, retry: vi.fn() };
}

const READY = section();

/** São Paulo's four numbers, mapped from the segments as the Command Center maps them. */
function saoPaulo(state: SectionState = READY): KeyNumbersProps {
  return {
    rain: {
      value: weatherCard.rain_risk,
      source: weatherCard.confidence,
      forecast: weather.sessions.find((row) => row.name === "Race")?.forecast ?? null,
      state,
    },
    pit: { ...pitLaneFigure(strategy), state },
    title: { stakes: stakes.drivers, state },
    history: { record: circuit.record, state },
  };
}

/** A tile as [figure, caption], found by its label. */
function tile(label: string): [string | null | undefined, string | null | undefined] {
  const root = screen.getByRole("group", { name: label });
  return [root.querySelector("p.mt-2")?.textContent, root.querySelector("p.line-clamp-2")?.textContent];
}

describe("KeyNumbers", () => {
  beforeEach(() => {
    vi.mocked(useReducedMotion).mockReturnValue(true);
  });

  it("reads São Paulo's race-day rain, pit-lane time, decided title and pole record", () => {
    const { container } = render(<KeyNumbers {...saoPaulo()} />);

    expect(tile("Race-day rain")).toEqual(["21%", "Race-day forecast (Open-Meteo)"]);
    expect(tile("Pit lane time")).toEqual(["23.5s", "Median of 34 stops · 2025 São Paulo Grand Prix"]);
    expect(tile("Title gap")).toEqual(["Decided", "Kimi Antonelli has clinched the title"]);
    expect(tile("Pole → win here")).toEqual(["6/10", "Poles converted to wins in the last 10 races here"]);
    // The rain tile takes its accent from the rain band, and draws the race's sky.
    expect(container.querySelector(".h-\\[2px\\]")).toHaveStyle({ backgroundColor: "#FFF200" });
    expect(container.querySelectorAll("svg[viewBox='0 0 64 64']")).toHaveLength(1);
  });

  it("gives the title gap to the closest rival while the title is open", () => {
    render(<KeyNumbers {...saoPaulo()} title={{ stakes: STAKES_2026.afterRound18.drivers, state: READY }} />);

    expect(tile("Title gap")).toEqual(["123pts", "Kimi Antonelli leads George Russell · 125 still on offer"]);
  });

  it("says when the leader has nobody to measure against", () => {
    // The backend's lone-entry table: one row, nobody alive to beat, nothing to clinch.
    const drivers = STAKES_2026.afterRound1.drivers;
    if (!drivers) throw new Error("no drivers' table");
    const lone = { ...drivers, contenders: [drivers.leader], rivals_alive: 0, clinch: null };
    render(<KeyNumbers {...saoPaulo()} title={{ stakes: lone, state: READY }} />);

    expect(tile("Title gap")).toEqual(["—", "George Russell leads unopposed"]);
  });

  it("shows dashes and plain reasons where Las Vegas and Madring have no numbers yet", () => {
    const lasVegas = SESSION_WEATHER_2026.lasVegasCard;
    const { container } = render(
      <KeyNumbers
        rain={{ value: lasVegas.rain_risk, source: lasVegas.confidence, forecast: null, state: READY }}
        pit={{ ...pitLaneFigure(STRATEGY_2026.madringNoEdition), state: READY }}
        title={{ stakes: STAKES_2026.preseason.drivers, state: READY }}
        history={{ record: CIRCUIT_RECORDS.madring2026.record, state: READY }}
      />,
    );

    expect(tile("Race-day rain")).toEqual(["—", "The race-day forecast opens on 7 Nov."]);
    expect(tile("Pit lane time")).toEqual(["—", "No edition of this circuit measured"]);
    expect(tile("Title gap")).toEqual(["—", "Standings unavailable"]);
    expect(tile("Pole → win here")).toEqual(["—", "No earlier race at this circuit"]);
    expect(container.querySelector("svg[viewBox='0 0 64 64']")).not.toBeInTheDocument();
    expect(container.querySelector(".h-\\[2px\\]")).toHaveStyle({ backgroundColor: "#3A4254" });
  });

  it("reads a missing circuit record as no earlier race", () => {
    render(<KeyNumbers {...saoPaulo()} history={{ record: undefined, state: READY }} />);

    expect(tile("Pole → win here")).toEqual(["—", "No earlier race at this circuit"]);
  });

  it("holds each tile at an ellipsis while its segment loads, with no caption and no rain glyph", () => {
    const { container } = render(<KeyNumbers {...saoPaulo(section("pending"))} />);

    expect(screen.getAllByText("…")).toHaveLength(4);
    // Nothing has loaded, so no caption may claim "No earlier race" or "Standings unavailable".
    expect(tile("Pole → win here")).toEqual(["…", ""]);
    expect(tile("Title gap")).toEqual(["…", ""]);
    expect(container.querySelector("svg[viewBox='0 0 64 64']")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("keeps every figure when a refresh fails, marked stale with a retry", async () => {
    // 2026-11-06: all four tiles read "Unavailable" over real data after a failed revalidation.
    const stale = section("stale", "Request failed: 500 Internal Server Error");
    const { container } = render(<KeyNumbers {...saoPaulo(stale)} />);

    expect(tile("Race-day rain")).toEqual(["21%", "Race-day forecast (Open-Meteo)"]);
    expect(tile("Pit lane time")).toEqual(["23.5s", "Median of 34 stops · 2025 São Paulo Grand Prix"]);
    expect(tile("Title gap")).toEqual(["Decided", "Kimi Antonelli has clinched the title"]);
    expect(tile("Pole → win here")).toEqual(["6/10", "Poles converted to wins in the last 10 races here"]);
    expect(screen.queryByText("Unavailable")).not.toBeInTheDocument();
    expect(screen.getAllByText("Couldn't refresh")).toHaveLength(4);
    expect(container.querySelectorAll("svg[viewBox='0 0 64 64']")).toHaveLength(1);

    await userEvent.click(
      within(screen.getByRole("group", { name: "Title gap" })).getByRole("button", { name: "Retry" }),
    );
    expect(stale.retry).toHaveBeenCalledTimes(1);
  });

  it("marks only the tile whose segment failed to refresh", () => {
    render(
      <KeyNumbers
        {...saoPaulo()}
        rain={{ ...saoPaulo().rain, state: section("stale", "Could not reach the server.") }}
      />,
    );

    expect(
      within(screen.getByRole("group", { name: "Race-day rain" })).getByText("Couldn't refresh"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Couldn't refresh")).toHaveLength(1);
  });

  it("says Unavailable, and why, only when a tile's segment has no data", async () => {
    const failed = section("failed", "Could not reach the server.");
    const { container } = render(<KeyNumbers {...saoPaulo(failed)} />);

    expect(screen.getAllByText("Unavailable")).toHaveLength(4);
    expect(tile("Race-day rain")).toEqual(["Unavailable", "Could not reach the server."]);
    expect(tile("Pole → win here")).toEqual(["Unavailable", "Could not reach the server."]);
    expect(container.querySelector("svg[viewBox='0 0 64 64']")).not.toBeInTheDocument();

    await userEvent.click(
      within(screen.getByRole("group", { name: "Pole → win here" })).getByRole("button", { name: "Retry" }),
    );
    expect(failed.retry).toHaveBeenCalledTimes(1);
  });
});
