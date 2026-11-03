import { render, screen } from "@testing-library/react";
import { useReducedMotion } from "framer-motion";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CIRCUIT_RECORDS, SAO_PAULO_2026, SESSION_WEATHER_2026, STAKES_2026 } from "@/test/fixtures";

import { KeyNumbers, type KeyNumbersProps, type TileState } from "./KeyNumbers";

import type * as FramerMotion from "framer-motion";

vi.mock("framer-motion", async (importOriginal) => ({
  ...(await importOriginal<typeof FramerMotion>()),
  useReducedMotion: vi.fn(),
}));

const { weatherCard, weather, pitModel, stakes, circuit } = SAO_PAULO_2026;

/** São Paulo's four numbers, mapped from the segments as the Command Center maps them. */
function saoPaulo(state: TileState = "ready"): KeyNumbersProps {
  return {
    rain: {
      value: weatherCard.rain_risk,
      source: weatherCard.confidence,
      forecast: weather.sessions.find((row) => row.name === "Race")?.forecast ?? null,
      state,
    },
    pit: {
      lossSeconds: pitModel.pit_loss_seconds,
      detail: `Undercut ${pitModel.undercut_delta}s · overcut ${pitModel.overcut_delta}s · modeled`,
      state,
    },
    title: { stakes: stakes.drivers, state },
    history: { record: circuit.record, state },
  };
}

/** A tile as [figure, caption], found by its label. */
function tile(label: string): [string | null | undefined, string | null | undefined] {
  const root = screen.getByText(label).closest(".relative");
  return [root?.querySelector("p.mt-2")?.textContent, root?.lastElementChild?.textContent];
}

describe("KeyNumbers", () => {
  beforeEach(() => {
    vi.mocked(useReducedMotion).mockReturnValue(true);
  });

  it("reads São Paulo's race-day rain, pit loss, decided title and pole record", () => {
    const { container } = render(<KeyNumbers {...saoPaulo()} />);

    expect(tile("Race-day rain")).toEqual(["21%", "Race-day forecast (Open-Meteo)"]);
    expect(tile("Pit lane loss")).toEqual(["21.9s", "Undercut 1.4s · overcut 0.9s · modeled"]);
    expect(tile("Title gap")).toEqual(["Decided", "Kimi Antonelli has clinched the title"]);
    expect(tile("Pole → win here")).toEqual(["6/10", "Poles converted to wins in the last 10 races here"]);
    // The rain tile takes its accent from the rain band, and draws the race's sky.
    expect(container.querySelector(".h-\\[2px\\]")).toHaveStyle({ background: "#FFF200" });
    expect(container.querySelectorAll("svg[viewBox='0 0 64 64']")).toHaveLength(1);
  });

  it("gives the title gap to the closest rival while the title is open", () => {
    render(<KeyNumbers {...saoPaulo()} title={{ stakes: STAKES_2026.afterRound18.drivers, state: "ready" }} />);

    expect(tile("Title gap")).toEqual(["123pts", "Kimi Antonelli leads George Russell · 125 still on offer"]);
  });

  it("says when the leader has nobody to measure against", () => {
    // The backend's lone-entry table: one row, nobody alive to beat, nothing to clinch.
    const drivers = STAKES_2026.afterRound1.drivers;
    if (!drivers) throw new Error("no drivers' table");
    const lone = { ...drivers, contenders: [drivers.leader], rivals_alive: 0, clinch: null };
    render(<KeyNumbers {...saoPaulo()} title={{ stakes: lone, state: "ready" }} />);

    expect(tile("Title gap")).toEqual(["—", "George Russell leads unopposed"]);
  });

  it("shows dashes and plain reasons where Las Vegas and Madring have no numbers yet", () => {
    const lasVegas = SESSION_WEATHER_2026.lasVegasCard;
    const { container } = render(
      <KeyNumbers
        rain={{ value: lasVegas.rain_risk, source: lasVegas.confidence, forecast: null, state: "ready" }}
        pit={{ lossSeconds: null, detail: "Baseline model unavailable", state: "ready" }}
        title={{ stakes: STAKES_2026.preseason.drivers, state: "ready" }}
        history={{ record: CIRCUIT_RECORDS.madring2026.record, state: "ready" }}
      />,
    );

    expect(tile("Race-day rain")).toEqual(["—", "External forecast feed not connected"]);
    expect(tile("Pit lane loss")).toEqual(["No model", "Baseline model unavailable"]);
    expect(tile("Title gap")).toEqual(["—", "Standings unavailable"]);
    expect(tile("Pole → win here")).toEqual(["—", "No earlier race at this circuit"]);
    expect(container.querySelector("svg[viewBox='0 0 64 64']")).not.toBeInTheDocument();
    expect(container.querySelector(".h-\\[2px\\]")).toHaveStyle({ background: "#3A4254" });
  });

  it("reads a missing circuit record as no earlier race", () => {
    render(<KeyNumbers {...saoPaulo()} history={{ record: undefined, state: "ready" }} />);

    expect(tile("Pole → win here")).toEqual(["—", "No earlier race at this circuit"]);
  });

  it("holds each tile at an ellipsis while its segment loads, without the rain glyph", () => {
    const { container } = render(<KeyNumbers {...saoPaulo("pending")} />);

    expect(screen.getAllByText("…")).toHaveLength(4);
    expect(container.querySelector("svg[viewBox='0 0 64 64']")).not.toBeInTheDocument();
  });

  it("says a tile's segment failed rather than showing a stale figure", () => {
    render(<KeyNumbers {...saoPaulo("failed")} />);

    expect(screen.getAllByText("Unavailable")).toHaveLength(4);
    expect(tile("Race-day rain")[1]).toBe("Race-day forecast (Open-Meteo)");
  });
});
