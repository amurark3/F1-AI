import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PROFILE_PAGES_2026 } from "@/test/fixtures";

import { PointsByWeekend } from "./PointsByWeekend";

const { mercedes } = PROFILE_PAGES_2026;

describe("PointsByWeekend", () => {
  it("heads the chart with the computed finding and names what it counts", () => {
    render(<PointsByWeekend profile={mercedes} />);

    expect(
      screen.getByRole("heading", { level: 3, name: "Scored in every round; the Chinese GP was the biggest haul" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Including sprints")).toBeInTheDocument();
    expect(screen.getByText("Constructor points per weekend · best weekend highlighted")).toBeInTheDocument();
  });

  it("draws one column per completed round, the best in the team colour", () => {
    render(<PointsByWeekend profile={mercedes} />);

    const list = screen.getByRole("list", { name: "Constructor points by round" });
    const columns = within(list).getAllByRole("listitem");
    expect(columns).toHaveLength(20);
    expect(columns[1]).toHaveAttribute("title", "R2 Chinese GP: 55 points");
    const best = columns[1]?.querySelector<HTMLElement>("[data-bar]");
    const other = columns[0]?.querySelector<HTMLElement>("[data-bar]");
    expect(best?.style.backgroundColor).toBe("rgb(39, 244, 210)");
    expect(other?.style.backgroundColor).toContain("color-mix");
  });

  it("says no points yet, and draws no bars, when no weekend scored", () => {
    const none = { ...mercedes, rounds: mercedes.rounds.map((round) => ({ ...round, points: 0 })) };
    render(<PointsByWeekend profile={none} />);

    expect(screen.getByRole("heading", { level: 3, name: "No points yet" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(20);
    expect(document.querySelector("[data-bar]")).toBeNull();
  });
});
