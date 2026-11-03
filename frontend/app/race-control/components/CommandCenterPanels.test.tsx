import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RISK_REGISTERS_2026, STRATEGY_2026 } from "@/test/fixtures";

import { BaselineStrategyPanel, RiskRegisterPanel } from "./CommandCenterPanels";

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

/** A pit-model stat as [value, note], found by its label. */
function stat(label: string): [string | null | undefined, string | null] {
  const card = present(screen.getByText(label).closest("div.rounded-lg"), `${label} stat`);
  const note = card.querySelector("span");
  return [card.querySelector("p.text-lg")?.textContent, note ? note.textContent : null];
}

/** Where the stint bar puts a lap, as the share of the race the panel draws. */
function lapShare(lap: number, laps: number): number {
  return (lap / laps) * 100;
}

describe("BaselineStrategyPanel", () => {
  it("plans São Paulo from the Interlagos 2022 telemetry, at high confidence", () => {
    const { container } = render(<BaselineStrategyPanel context={STRATEGY_2026.saoPaulo} />);

    expect(confidencePill()).toHaveTextContent("high");
    expect(confidencePill()).toHaveStyle({ color: "#3671C6" });
    expect(
      screen.getByText(
        "Field ran a Soft-to-Soft two-stop here in 2022 (median first stop L22, 20-car sample); keep a one-stop branch open if degradation shifts the crossover.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Pit loss & tyre windows from 2022 telemetry · 20 cars · undercut/overcut modeled"),
    ).toBeInTheDocument();

    // Measured windows carry no "modeled" chip; the flag sits on the median first stop.
    const timeline = present(screen.getByText("Stint windows").parentElement, "stint header");
    expect(within(timeline).queryByText("modeled")).not.toBeInTheDocument();
    expect(screen.getByText("L22").parentElement).toHaveStyle({ left: `${lapShare(22, 71)}%` });
    expect(screen.getByText("First-stop window L17–L35")).toBeInTheDocument();
    expect(screen.getByText("L71")).toBeInTheDocument();
    const band = present(container.querySelector(".border-dashed"), "first-stop band") as HTMLElement;
    expect(band.style.left).toBe(`${lapShare(17, 71)}%`);
    expect(band.style.width).toBe(`${lapShare(35, 71) - lapShare(17, 71)}%`);
    for (const label of screen.getAllByText("Soft")) expect(label).toHaveStyle({ color: "#FF3B3B" });

    // The undercut and overcut deltas are always modeled; traffic here is measured.
    expect(stat("Pit loss")).toEqual(["21.9s", null]);
    expect(stat("Undercut")).toEqual(["1.4s", "modeled"]);
    expect(stat("Overcut")).toEqual(["0.9s", "modeled"]);
    expect(stat("Traffic")).toEqual(["medium", null]);
  });

  it("labels the heuristic plan when no edition's telemetry can be loaded", () => {
    render(<BaselineStrategyPanel context={STRATEGY_2026.saoPauloWithoutReference} />);

    expect(confidencePill()).toHaveTextContent("medium");
    expect(confidencePill()).toHaveStyle({ color: "#FFF200" });
    expect(
      screen.getByText(
        "Model a medium-to-hard one-stop around L30; keep a two-stop branch open if tyre age exceeds the working life before the stop.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Planning heuristics · no completed edition available for telemetry")).toBeInTheDocument();

    const timeline = present(screen.getByText("Stint windows").parentElement, "stint header");
    expect(within(timeline).getByText("modeled")).toBeInTheDocument();
    expect(screen.getByText("First-stop window L26–L40")).toBeInTheDocument();
    expect(screen.getByText("Medium")).toHaveStyle({ color: "#FFF200" });
    expect(screen.getByText("Hard")).toHaveStyle({ color: "#EBEBEB" });

    expect(stat("Pit loss")).toEqual(["21s", null]);
    expect(stat("Traffic")).toEqual(["medium", "modeled"]);
  });

  it("draws a compound the timing feed never named in neutral grey", () => {
    render(<BaselineStrategyPanel context={STRATEGY_2026.spaWithoutCompounds} />);

    const labels = screen.getAllByText("Unknown");
    expect(labels).toHaveLength(2);
    for (const label of labels) expect(label).toHaveStyle({ color: "#8A93A6" });
  });

  it("holds a draft plan with no model numbers until the strategy context arrives", () => {
    render(<BaselineStrategyPanel context={undefined} />);

    expect(confidencePill()).toHaveTextContent("draft");
    expect(confidencePill()).toHaveStyle({ color: "#3671C6" });
    expect(
      screen.getByText("Strategy context will populate when the next race and prediction snapshot are available."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/telemetry/)).not.toBeInTheDocument();
    expect(screen.queryByText("Stint windows")).not.toBeInTheDocument();
    for (const label of ["Pit loss", "Undercut", "Overcut", "Traffic"]) {
      expect(stat(label)).toEqual(["No model", null]);
    }
  });
});

describe("RiskRegisterPanel", () => {
  it("grades São Paulo's risks from the race-day forecast and the constructors' gap", () => {
    render(<RiskRegisterPanel risks={RISK_REGISTERS_2026.saoPaulo} />);

    const cards = screen.getAllByRole("listitem");
    expect(cards.map((card) => within(card).getByText(/^(High|Medium|Low)$/).textContent)).toEqual(["Medium", "Low"]);
    expect(within(cards[0]).getByText("Mixed conditions possible")).toBeInTheDocument();
    expect(
      within(cards[0]).getByText("Live forecast shows 21% rain probability — keep the dry/wet crossover branch ready."),
    ).toBeInTheDocument();
    expect(cards[0]).toHaveStyle({ borderLeft: "3px solid #FFF200", animationDelay: "0s" });
    expect(within(cards[1]).getByText("Rival offset plans")).toBeInTheDocument();
    expect(cards[1]).toHaveStyle({ borderLeft: "3px solid #00FF78", animationDelay: "0.08s" });
    expect(within(cards[1]).getByText("Low")).toHaveStyle({ color: "#00FF78" });
  });

  it("marks a street circuit's safety-car exposure High, and an offline forecast as such", () => {
    render(<RiskRegisterPanel risks={RISK_REGISTERS_2026.lasVegas} />);

    const [street, weather] = screen.getAllByRole("listitem");
    expect(within(street).getByText("Safety car exposure")).toBeInTheDocument();
    expect(street).toHaveStyle({ borderLeft: "3px solid #FF4655" });
    expect(within(street).getByText("High")).toHaveStyle({ color: "#FF4655" });
    expect(within(weather).getByText("Weather feed offline")).toBeInTheDocument();
    expect(screen.queryByText("No risks graded for this weekend.")).not.toBeInTheDocument();
  });

  it("says so when there is no weekend to grade", () => {
    render(<RiskRegisterPanel risks={RISK_REGISTERS_2026.noRace} />);

    expect(screen.getByRole("heading", { name: "Weekend risks" })).toBeInTheDocument();
    expect(screen.getByText("No risks graded for this weekend.")).toBeInTheDocument();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });
});
