import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RISK_REGISTERS_2026 } from "@/test/fixtures";

import { RiskRegisterPanel } from "./CommandCenterPanels";

describe("RiskRegisterPanel", () => {
  it("grades São Paulo's risks from the race-day forecast and the constructors' gap", () => {
    render(<RiskRegisterPanel risks={RISK_REGISTERS_2026.saoPaulo} />);

    const cards = screen.getAllByRole("listitem");
    expect(cards.map((card) => within(card).getByText(/^(High|Medium|Low)$/).textContent)).toEqual(["Medium", "Low"]);
    expect(within(cards[0]).getByText("Mixed conditions possible")).toBeInTheDocument();
    expect(
      within(cards[0]).getByText(
        "Race-day forecast (Open-Meteo): 21% peak rain probability in the race window — keep the dry/wet crossover branch ready.",
      ),
    ).toBeInTheDocument();
    expect(cards[0]).toHaveStyle({ borderLeft: "3px solid #FFF200", animationDelay: "0s" });
    expect(within(cards[1]).getByText("Rival offset plans")).toBeInTheDocument();
    expect(cards[1]).toHaveStyle({ borderLeft: "3px solid #00FF78", animationDelay: "0.08s" });
    expect(within(cards[1]).getByText("Low")).toHaveStyle({ color: "#00FF78" });
  });

  it("marks a street circuit's safety-car exposure High, and a race with no forecast yet Medium with why", () => {
    render(<RiskRegisterPanel risks={RISK_REGISTERS_2026.lasVegas} />);

    const [street, weather] = screen.getAllByRole("listitem");
    expect(within(street).getByText("Safety car exposure")).toBeInTheDocument();
    expect(street).toHaveStyle({ borderLeft: "3px solid #FF4655" });
    expect(within(street).getByText("High")).toHaveStyle({ color: "#FF4655" });
    expect(within(weather).getByText("Race-day forecast unavailable")).toBeInTheDocument();
    expect(within(weather).getByText("Medium")).toHaveStyle({ color: "#FFF200" });
    expect(within(weather).getByText(/^The race-day forecast opens on 7 Nov\./)).toBeInTheDocument();
    expect(within(weather).queryByText(/%/)).not.toBeInTheDocument();
    expect(screen.queryByText("No risks graded for this weekend.")).not.toBeInTheDocument();
  });

  it("says so when there is no weekend to grade", () => {
    render(<RiskRegisterPanel risks={RISK_REGISTERS_2026.noRace} />);

    expect(screen.getByRole("heading", { name: "Weekend risks" })).toBeInTheDocument();
    expect(screen.getByText("No risks graded for this weekend.")).toBeInTheDocument();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });
});
