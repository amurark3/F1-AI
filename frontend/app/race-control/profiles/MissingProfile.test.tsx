import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MissingProfile } from "./MissingProfile";

describe("MissingProfile", () => {
  it("names the season, the kind and the id, and links back to the list", () => {
    render(
      <MissingProfile year={2026} what="team" id="lotus" backHref="/race-control/constructors" backLabel="All teams" />,
    );

    expect(screen.getByText("No 2026 team with the id “lotus”.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All teams" })).toHaveAttribute("href", "/race-control/constructors");
  });
});
