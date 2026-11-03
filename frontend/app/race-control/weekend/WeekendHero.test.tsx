import { act, render, screen, within } from "@testing-library/react";
import { useReducedMotion } from "framer-motion";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { formatLocal } from "@/app/lib/formatTime";
import { CIRCUIT_RECORDS, SAO_PAULO_2026 } from "@/test/fixtures";

import { WeekendHero } from "./WeekendHero";

import type * as FramerMotion from "framer-motion";

vi.mock("framer-motion", async (importOriginal) => ({
  ...(await importOriginal<typeof FramerMotion>()),
  useReducedMotion: vi.fn(),
}));

/** When the São Paulo fixtures were captured. */
const CAPTURED = Date.UTC(2026, 10, 3, 7, 50);
const { race, totalRounds, circuit, weather } = SAO_PAULO_2026;
const LONG_BEACH = CIRCUIT_RECORDS.longBeach1983;

function renderSaoPaulo(overrides: Partial<Parameters<typeof WeekendHero>[0]> = {}) {
  return render(
    <WeekendHero
      race={race}
      totalRounds={totalRounds}
      circuit={circuit}
      circuitLoading={false}
      forecast={weather.sessions}
      {...overrides}
    />,
  );
}

/** The countdown's cells as "unit value", e.g. "days 03". */
function countdown(): string[] {
  return ["days", "hrs", "min", "sec"].map((unit) => {
    const cell = screen.getByText(unit).parentElement;
    return `${unit} ${cell?.firstElementChild?.textContent}`;
  });
}

describe("WeekendHero", () => {
  beforeEach(() => {
    vi.mocked(useReducedMotion).mockReturnValue(true);
    vi.useFakeTimers({ now: CAPTURED });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("introduces São Paulo: the round, country, status, circuit, dates and weather", () => {
    renderSaoPaulo();

    expect(screen.getByText("Round 20 / 23 · Brazil")).toBeInTheDocument();
    expect(screen.getByText("Upcoming")).toHaveStyle({ color: "#4C8DFF" });
    expect(screen.getByRole("heading", { level: 1, name: "São Paulo Grand Prix" })).toBeInTheDocument();
    expect(screen.getByText("Autódromo José Carlos Pace · São Paulo")).toBeInTheDocument();
    const first = formatLocal("2026-11-06T15:30:00Z", "weekday", "—");
    const last = formatLocal("2026-11-08T17:00:00Z", "weekday", "—");
    expect(screen.getByText(`${first} → ${last}`)).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Weather by session" })).getAllByRole("listitem")).toHaveLength(5);
    expect(screen.getByRole("img", { name: "Autódromo José Carlos Pace layout" })).toBeInTheDocument();
    expect(screen.getByText("Layout · MultiViewer 2026")).toBeInTheDocument();
    expect(screen.getByText("Lap record")).toBeInTheDocument();
  });

  it("counts down to the next session a second at a time", () => {
    renderSaoPaulo();

    expect(screen.getByText("Practice 1")).toHaveClass("text-[#FF4655]");
    expect(countdown()).toEqual(["days 03", "hrs 07", "min 40", "sec 00"]);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(countdown()).toEqual(["days 03", "hrs 07", "min 39", "sec 59"]);
  });

  it("shows the session on track as live", () => {
    vi.setSystemTime(Date.UTC(2026, 10, 8, 17, 30));
    renderSaoPaulo();

    expect(screen.getByText("Live now · Race")).toBeInTheDocument();
    expect(screen.queryByText("days")).not.toBeInTheDocument();
  });

  it("says the weekend is complete once the race's two hours are up", () => {
    vi.setSystemTime(Date.UTC(2026, 10, 8, 19, 0));
    renderSaoPaulo();

    expect(screen.getByText("Weekend complete")).toBeInTheDocument();
  });

  it("server-renders dashes and UTC dates, as the server has no honest now", () => {
    const html = renderToString(
      <WeekendHero race={race} totalRounds={totalRounds} circuit={circuit} circuitLoading={false} forecast={[]} />,
    );

    expect(html).toContain('Next · <span class="text-[#FF4655]">—</span>');
    expect(html.match(/>--</g)).toHaveLength(4);
    expect(html).toContain("Fri, Nov 6<!-- --> → <!-- -->Sun, Nov 8");
    expect(html).not.toContain("Weather by session");
  });

  it("holds the map slot while the circuit segment loads, naming the circuit from the schedule", () => {
    const { container } = renderSaoPaulo({ circuit: undefined, circuitLoading: true });

    expect(screen.getByText("Autódromo José Carlos Pace (Interlagos) · São Paulo")).toBeInTheDocument();
    expect(container.querySelector(".motion-safe\\:animate-pulse")).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /layout$/ })).not.toBeInTheDocument();
    expect(screen.queryByText("Circuit map unavailable")).not.toBeInTheDocument();
    // The schedule's facts stand in for f1db's record.
    expect(screen.getByText("Lap record")).toBeInTheDocument();
    expect(screen.queryByText("Turns")).not.toBeInTheDocument();
  });

  it("shows Long Beach 1983 once, with no map and no schedule facts", () => {
    render(
      <WeekendHero
        race={LONG_BEACH.race}
        totalRounds={null}
        circuit={LONG_BEACH.circuit}
        circuitLoading={false}
        forecast={[]}
      />,
    );

    expect(screen.getByText("Round 2 · USA")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toHaveStyle({ color: "#7F8797" });
    // f1db names the circuit after its town, so the town is not repeated.
    expect(screen.getByText("Long Beach")).toBeInTheDocument();
    expect(screen.getByText("Circuit map unavailable")).toBeInTheDocument();
    expect(screen.getByText("Weekend complete")).toBeInTheDocument();
    expect(screen.getByText("Turns")).toBeInTheDocument();
    expect(screen.queryByText("Lap record")).not.toBeInTheDocument();
  });

  it("names the venue from the schedule's location while neither source knows the circuit", () => {
    render(<WeekendHero race={LONG_BEACH.race} totalRounds={null} circuit={undefined} circuitLoading forecast={[]} />);

    expect(screen.getByText("California, USA · California")).toBeInTheDocument();
    expect(screen.queryByText("Circuit map unavailable")).not.toBeInTheDocument();
    expect(screen.queryByRole("term")).not.toBeInTheDocument();
  });

  it("leaves out what the schedule does not give: country, session times", () => {
    renderSaoPaulo({ race: { ...race, country: null, sessions: {} } });

    expect(screen.getByText("Round 20 / 23")).toBeInTheDocument();
    expect(screen.queryByText(/→/)).not.toBeInTheDocument();
    expect(screen.getByText("Weekend complete")).toBeInTheDocument();
  });

  it("shows a status it has no label for as sent", () => {
    renderSaoPaulo({ race: { ...race, status: "postponed" } });

    expect(screen.getByText("postponed")).toHaveStyle({ color: "#7F8797" });
  });

  it("marks a weekend in progress as live", () => {
    renderSaoPaulo({ race: { ...race, status: "in_progress" } });

    expect(screen.getByText("Weekend live")).toHaveStyle({ color: "#FF4655" });
  });
});
