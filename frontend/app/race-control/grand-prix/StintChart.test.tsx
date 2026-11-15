import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MEXICO_CITY_2026 } from "@/test/fixtures";

import { StintChart } from "./StintChart";

import type { DriverStint, DriverStrategy, RaceStrategyResponse } from "./strategyModel";

const MEXICO = MEXICO_CITY_2026.strategy;

function driver(overrides: Partial<DriverStrategy>): DriverStrategy {
  return { ...MEXICO.drivers[0], ...overrides };
}

function stint(overrides: Partial<DriverStint>): DriverStint {
  return { ...MEXICO.drivers[0].stints[0], ...overrides };
}

describe("StintChart on Mexico City", () => {
  it("titles itself from the red flag and the cars it gave a free change", () => {
    render(<StintChart data={MEXICO} />);

    const changed = MEXICO.drivers.filter((row) => row.red_flag_changes > 0).length;
    expect(
      screen.getByRole("heading", { name: `The red flag on lap 45 gave ${changed} drivers a free tyre change` }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Ordered by the classification · 71 laps/)).toBeInTheDocument();
  });

  it("reads each of the five retirements DNF with its reason in the tooltip, never NC", () => {
    render(<StintChart data={MEXICO} />);

    const retired = MEXICO.drivers.filter((row) => row.status === "dnf");
    expect(retired).toHaveLength(5);
    for (const row of retired) {
      const line = screen.getByTitle(new RegExp(`^${row.driver_code}: Retired: ${row.reason}`));
      expect(within(line).getByText("DNF")).toBeInTheDocument();
      expect(within(line).getByText(`DNF · L${row.laps_completed}`)).toBeInTheDocument();
    }
    expect(screen.queryByText("NC")).not.toBeInTheDocument();
    expect(screen.getByTitle(/^VER: Took the flag/)).toHaveTextContent("1");
  });

  it("draws the VSC and safety car bands and the red flag line, with the flag on its own tier", () => {
    render(<StintChart data={MEXICO} />);

    expect(screen.getByTitle("VSC laps 7-8")).toBeInTheDocument();
    expect(screen.getByTitle("SC laps 44-44")).toBeInTheDocument();
    expect(screen.getByTitle("SC laps 59-62")).toBeInTheDocument();
    expect(screen.getByTitle("Red flag after lap 45")).toBeInTheDocument();
    expect(screen.getByText("RED FLAG · L45")).toBeInTheDocument();
    // Bands low, the red flag high: two tiers, so the labels never share a spot.
    expect(screen.getByTitle("SC laps 44-44").className).toContain("top-[18px]");
    expect(screen.getByTitle("Red flag after lap 45").className).toContain("top-0");
  });

  it("keys the compounds and marks it uses, and notes the quickest stop", () => {
    render(<StintChart data={MEXICO} />);

    const key = screen.getByRole("list", { name: "Tyre compounds and marks" });
    expect(within(key).getByText("Soft")).toBeInTheDocument();
    expect(within(key).getByText("Red flag change")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Stint marks" })).toHaveTextContent("Used set");
    expect(screen.getByText(/Quickest stop:/)).toBeInTheDocument();
  });
});

describe("StintChart in its other states", () => {
  it("titles a race with no red flag by its stops, and draws no flag line", () => {
    const quiet: RaceStrategyResponse = { ...MEXICO, neutralisations: [], warnings: undefined, fastest_stop: null };
    render(<StintChart data={quiet} />);

    expect(
      screen.getByRole("heading", { name: `${MEXICO.stops_made} pit stops by 22 cars over 71 laps` }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/RED FLAG/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Quickest stop/)).not.toBeInTheDocument();
  });

  it("lists no unrecorded-compound swatch when every stint's compound is known", () => {
    render(<StintChart data={{ ...MEXICO, drivers: MEXICO.drivers.slice(0, 1) }} />);
    expect(screen.getByRole("list", { name: "Tyre compounds and marks" })).not.toHaveTextContent("Not recorded");
  });

  it("draws nothing over the lanes when the neutralisations are unknown or only a band", () => {
    const { rerender } = render(<StintChart data={{ ...MEXICO, neutralisations: null }} />);
    expect(screen.queryByTitle(/laps/)).not.toBeInTheDocument();

    rerender(<StintChart data={{ ...MEXICO, neutralisations: [{ kind: "sc", start_lap: 3, end_lap: 4 }] }} />);
    expect(screen.getByTitle("SC laps 3-4")).toBeInTheDocument();
    expect(screen.queryByText(/RED FLAG/)).not.toBeInTheDocument();
  });

  it("says why there is no chart, from the warning when there is one", () => {
    const { rerender } = render(<StintChart />);
    expect(screen.getByText(/appears here once the race has run/)).toBeInTheDocument();

    rerender(<StintChart data={{ ...MEXICO, drivers: [], warnings: ["Tyre stint data is not available."] }} />);
    expect(screen.getByText("Tyre stint data is not available.")).toBeInTheDocument();

    rerender(<StintChart data={{ ...MEXICO, drivers: [], warnings: undefined }} />);
    expect(screen.getByText(/appears here once the race has run/)).toBeInTheDocument();
  });

  it("marks what is unknown: no classification, an unrecorded compound, a scrubbed set, a car that never ran", () => {
    const data: RaceStrategyResponse = {
      ...MEXICO,
      classification_source: null,
      neutralisations: null,
      drivers: [
        driver({
          driver_code: "AAA",
          status: null,
          finish_position: 3,
          laps_completed: null,
          reason: null,
          stints: [
            stint({ stint: 1, compound: null, fresh: false, tyre_life_start: null, laps: 3, start_lap: 1, end_lap: 3 }),
            stint({ stint: 2, compound: "WET", fresh: true, tyre_life_start: 0, laps: 40, start_lap: 4, end_lap: 43 }),
            stint({
              stint: 3,
              compound: "HARD",
              fresh: null,
              tyre_life_start: 5,
              laps: 28,
              start_lap: 44,
              end_lap: 71,
            }),
          ],
          total_laps: 71,
        }),
        driver({ driver_code: "BBB", status: "dns", finish_position: null, stints: [], total_laps: 0 }),
        driver({ driver_code: "CCC", status: "dsq", finish_position: null, stints: [], total_laps: 0 }),
        driver({
          driver_code: "DDD",
          status: "dnf",
          laps_completed: null,
          reason: null,
          stints: [stint({ laps: 71, start_lap: 1, end_lap: 71 })],
          total_laps: 71,
        }),
      ],
    };
    render(<StintChart data={data} />);

    expect(screen.getByText(/Ordered by finishing order/)).toBeInTheDocument();
    expect(screen.getByTitle(/Stint 1: Not recorded .*Tyre age not recorded/)).toBeInTheDocument();
    expect(screen.getByTitle(/Stint 2: Wet .*New set/)).toBeInTheDocument();
    expect(screen.getByTitle(/Stint 3: Hard .*Set had 5 lap\(s\) on it/)).toBeInTheDocument();
    expect(screen.getByText("Did not start")).toBeInTheDocument();
    expect(screen.getAllByText("No stint data published")).toHaveLength(1);
    expect(screen.getByText("DSQ")).toBeInTheDocument();
    // The Pos cell and the Stops column's tag, which has no lap count to add.
    expect(screen.getAllByText("DNF")).toHaveLength(2);
    expect(screen.getByRole("list", { name: "Tyre compounds and marks" })).toHaveTextContent("Not recorded");
  });
});
