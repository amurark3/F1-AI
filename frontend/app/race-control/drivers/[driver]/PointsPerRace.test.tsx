import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PROFILE_PAGES_2026 } from "@/test/fixtures";

import { PointsPerRace } from "./PointsPerRace";

const { hamilton } = PROFILE_PAGES_2026;

describe("PointsPerRace", () => {
  it("heads the chart with the computed finding", () => {
    render(<PointsPerRace profile={hamilton} />);

    expect(screen.getByRole("heading", { level: 3, name: "Scored in 19 of 20 races" })).toBeInTheDocument();
    expect(screen.getByText("Grand Prix points only · gold = win")).toBeInTheDocument();
  });

  it("makes the win gold and keys the colours", () => {
    render(<PointsPerRace profile={hamilton} />);

    const columns = within(screen.getByRole("list", { name: "Grand Prix points by round" })).getAllByRole("listitem");
    expect(columns).toHaveLength(20);
    expect(columns[6]?.querySelector<HTMLElement>("[data-bar]")?.style.backgroundColor).toBe("rgb(255, 201, 60)");
    const legend = within(screen.getByRole("list", { name: "Legend" })).getAllByRole("listitem");
    expect(legend.map((item) => item.textContent)).toEqual(["Win", "Points"]);
  });
});
