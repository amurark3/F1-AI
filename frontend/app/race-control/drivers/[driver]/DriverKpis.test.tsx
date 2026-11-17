import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PROFILE_PAGES_2026 } from "@/test/fixtures";

import { DriverKpis } from "./DriverKpis";

describe("DriverKpis", () => {
  it("shows Hamilton's four figures with the rounds behind them", () => {
    render(<DriverKpis profile={PROFILE_PAGES_2026.hamilton} />);

    expect(screen.getByText("Podiums").parentElement).toHaveTextContent("7of 20Win: Barcelona-Catalunya GP (R7)");
    expect(screen.getByText("Wins").parentElement).toHaveTextContent("1Round 7");
    expect(screen.getByText("Poles").parentElement).toHaveTextContent("1Mexican GP (R19)");
    expect(screen.getByText("Fastest laps").parentElement).toHaveTextContent("21 retirement (Spanish GP)");
  });
});
