import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PROFILE_PAGES_2026 } from "@/test/fixtures";

import { GridToFinish } from "./GridToFinish";

const { verstappen } = PROFILE_PAGES_2026;

describe("GridToFinish", () => {
  it("heads the chart with the computed finding and says what it counts", () => {
    render(<GridToFinish profile={verstappen} />);

    expect(
      screen.getByRole("heading", { level: 3, name: "Verstappen gained 53 places over the season" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/retirements count no places/)).toBeInTheDocument();
  });

  it("draws Verstappen's British GP retirement as DNF, never as a loss of places", () => {
    const { container } = render(<GridToFinish profile={verstappen} />);

    const columns = within(screen.getByRole("list", { name: "Places gained or lost by round" })).getAllByRole(
      "listitem",
    );
    expect(columns).toHaveLength(20);
    expect(columns[8]).toHaveTextContent("DNF");
    expect(columns[8]?.querySelector("[data-bar]")).toBeNull();
    expect(container.textContent).not.toContain("−13");
    expect(container.textContent).not.toContain("-13");
  });
});
