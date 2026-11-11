import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { rc } from "@/app/ui/tokens";
import { STRATEGY_2026 } from "@/test/fixtures";

import { compoundColor } from "../grand-prix/tyreCompounds";

import { BaselineStrategyPanel } from "./BaselineStrategyPanel";

import type { StrategyContext } from "./CommandCenterPanels";

/** Throws instead of asserting a type away, so a missing element fails the test. */
function present<T>(value: T | null | undefined, what: string): T {
  if (value == null) throw new Error(`${what} is missing`);
  return value;
}

/** The confidence pill beside the plan's title. */
function confidencePill(): HTMLElement {
  const heading = screen.getByRole("heading", { name: "Base race plan" });
  return present(heading.parentElement?.nextElementSibling as HTMLElement | null, "confidence pill");
}

/** A measured figure as [value, detail], found by its label. */
function stat(label: string): [string | null | undefined, string | null | undefined] {
  const card = present(screen.getByText(label).closest("div.rounded-lg"), `${label} stat`);
  const lines = card.querySelectorAll("p");
  return [lines[1]?.textContent, lines[2]?.textContent];
}

/** Where the stint bar puts a lap, as the share of the race the panel draws. */
function lapShare(lap: number, laps: number): number {
  return (lap / laps) * 100;
}

const SAO_PAULO = STRATEGY_2026.saoPaulo;
const SAO_PAULO_PLAN = present(SAO_PAULO.plan, "São Paulo plan");
const SAO_PAULO_SOURCE = present(SAO_PAULO.data_source, "São Paulo source");

describe("BaselineStrategyPanel", () => {
  it("plans São Paulo 2026 from the 2025 edition: the full sequence, its share, the year and the rules", () => {
    render(<BaselineStrategyPanel context={SAO_PAULO} />);

    expect(confidencePill()).toHaveTextContent("medium confidence");
    expect(confidencePill()).toHaveStyle({ color: rc.ink2 });
    expect(screen.getByText("17 finishers · 2025 edition · previous regulations")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Medium–Soft–Medium two-stop: 5 of 17 finishers ran it at the 2025 São Paulo Grand Prix (previous regulations), the winner among them. Soft–Medium–Medium two-stop was as common. 13 of 17 finishers stopped twice. First stops: median L21, middle half L17–L30.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("2025 São Paulo Grand Prix · previous regulations · 17 finishers")).toBeInTheDocument();
    expect(
      screen.getByText("OpenF1 stints · Jolpica pit stops · OpenF1 classification · OpenF1 pit-lane times"),
    ).toBeInTheDocument();
    // No wet race on the 3 Nov forecast (21%), so no rain note.
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });

  it("draws every stint of the headline sequence on its median stop laps", () => {
    const { container } = render(<BaselineStrategyPanel context={SAO_PAULO} />);

    const bands = [...container.querySelectorAll<HTMLElement>("[data-stint]")];
    expect(bands.map((band) => band.dataset.stint)).toEqual(["Medium", "Soft", "Medium"]);
    expect(bands.map((band) => [band.style.left, band.style.width])).toEqual([
      ["0%", `${lapShare(34, 71)}%`],
      [`${lapShare(34, 71)}%`, `${lapShare(50, 71) - lapShare(34, 71)}%`],
      [`${lapShare(50, 71)}%`, `${100 - lapShare(50, 71)}%`],
    ]);
    expect(within(bands[1]).getByText("Soft")).toHaveStyle({ color: compoundColor("SOFT") });
    expect(screen.getByText("L34").parentElement).toHaveStyle({ left: `${lapShare(34, 71)}%` });
    expect(screen.getByText("L50").parentElement).toHaveStyle({ left: `${lapShare(50, 71)}%` });
    expect(screen.getByText("L71")).toBeInTheDocument();
    expect(screen.getByText("5 of 17 finishers ran it")).toBeInTheDocument();
    expect(
      screen.getByText("Also run: Soft–Medium–Medium, 2 stops (5) · Hard–Medium–Medium, 2 stops (3)"),
    ).toBeInTheDocument();
  });

  it("shows only measured figures: pit-lane time, stops, first stop and sample", () => {
    render(<BaselineStrategyPanel context={SAO_PAULO} />);

    expect(screen.getByText("Measured in 2025")).toBeInTheDocument();
    expect(stat("Pit lane")).toEqual(["23.5s", "Median of 34 stops, entry to exit"]);
    expect(stat("Stops")).toEqual(["2", "13 of 17 finishers"]);
    expect(stat("First stop")).toEqual(["L21", "Middle half L17–L30"]);
    expect(stat("Sample")).toEqual(["17", "Classified finishers"]);
    // 6 Nov: an undercut of 1.4 s and an overcut of 0.9 s, both formulas.
    for (const gone of [/undercut/i, /overcut/i, /traffic/i, /modeled/i]) {
      expect(screen.queryByText(gone)).not.toBeInTheDocument();
    }
  });

  it("makes the dry plan the secondary branch when the race-day forecast is wet", () => {
    render(<BaselineStrategyPanel context={STRATEGY_2026.saoPauloWet} />);

    expect(screen.getByRole("note")).toHaveTextContent(
      "Race-day forecast (Open-Meteo): 92% peak rain probability in the race window, so this dry plan is the secondary branch.",
    );
  });

  it("invents nothing for a circuit with no edition to read", () => {
    const { container } = render(<BaselineStrategyPanel context={STRATEGY_2026.madringNoEdition} />);

    expect(confidencePill()).toHaveTextContent("no plan");
    expect(confidencePill()).toHaveStyle({ color: rc.ink3 });
    expect(screen.getByText(/^No baseline plan: this circuit has no completed race since 2023/)).toBeInTheDocument();
    expect(container.querySelector("[data-stint]")).not.toBeInTheDocument();
    expect(screen.queryByText("Pit lane")).not.toBeInTheDocument();
    expect(screen.queryByText(/^Also run/)).not.toBeInTheDocument();
  });

  it("waits with no plan and no figures until the strategy context arrives", () => {
    render(<BaselineStrategyPanel context={undefined} />);

    expect(confidencePill()).toHaveTextContent("no plan");
    expect(screen.getByText("The baseline plan has not arrived yet.")).toBeInTheDocument();
    expect(screen.queryByText("Pit lane")).not.toBeInTheDocument();
  });

  it("says what was not published rather than showing a number", () => {
    const thin: StrategyContext = {
      ...SAO_PAULO,
      primary_call: { ...SAO_PAULO.primary_call, confidence: "high", confidence_basis: null },
      data_source: {
        ...SAO_PAULO_SOURCE,
        event_name: null,
        previous_regulations: false,
        sample_size: null,
        sources: [],
      },
      plan: { ...SAO_PAULO_PLAN, total_laps: 0, stints: [] },
      alternatives: undefined,
      stop_counts: undefined,
      first_stop: null,
      pit_model: undefined,
    };
    const { container } = render(<BaselineStrategyPanel context={thin} />);

    expect(confidencePill()).toHaveStyle({ color: rc.blue });
    expect(screen.getByText("2025 edition · 0 finishers")).toBeInTheDocument();
    // A set changed under a red flag leaves no stop lap to draw the sequence on.
    expect(container.querySelector("[data-stint]")).not.toBeInTheDocument();
    expect(stat("Pit lane")).toEqual(["—", "Not published"]);
    expect(stat("Stops")).toEqual(["—", "Not published"]);
    expect(stat("First stop")).toEqual(["—", "No finisher stopped"]);
    expect(stat("Sample")).toEqual(["0", "Classified finishers"]);
  });

  it("counts a published pit-lane time with no stop count as zero stops, and draws a lap-less plan on one lap", () => {
    const sparse: StrategyContext = {
      ...SAO_PAULO,
      plan: { ...SAO_PAULO_PLAN, total_laps: 0 },
      pit_model: { pit_lane_seconds: 23.5, pit_lane_stops: null },
    };
    render(<BaselineStrategyPanel context={sparse} />);

    expect(stat("Pit lane")).toEqual(["23.5s", "Median of 0 stops, entry to exit"]);
    // Both ends of the axis read L1, and every stop sits at the far end.
    expect(screen.getAllByText("L1")).toHaveLength(2);
    expect(screen.getByText("L34").parentElement).toHaveStyle({ left: "100%" });
  });

  it("names one stop in the singular", () => {
    render(
      <BaselineStrategyPanel
        context={{ ...SAO_PAULO, alternatives: [{ compounds: ["Soft", "Medium"], stops: 1, drivers: 1 }] }}
      />,
    );

    expect(screen.getByText("Also run: Soft–Medium, 1 stop (1)")).toBeInTheDocument();
  });

  it("reads a payload from a backend older than P0b.4 without inventing a plan", () => {
    const legacy = {
      phase: "Pre-race build",
      primary_call: {
        title: "Base race plan",
        summary: "Field ran a Soft-to-Soft two-stop here in 2022.",
        confidence: "high",
      },
      data_source: { mode: "telemetry", edition_year: 2022, sample_size: 20 },
      assumptions: [],
    } as unknown as StrategyContext;
    render(<BaselineStrategyPanel context={legacy} />);

    expect(screen.getByText("Field ran a Soft-to-Soft two-stop here in 2022.")).toBeInTheDocument();
    expect(screen.queryByText("Pit lane")).not.toBeInTheDocument();
  });
});
