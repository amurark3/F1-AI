import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "@/test/render";

import Page, { metadata } from "./page";

describe("the Rulebook page", () => {
  it("renders the view without awaiting anything", () => {
    renderWithProviders(<Page />);

    expect(screen.getByRole("heading", { level: 1, name: "Ask the rulebook" })).toBeInTheDocument();
  });

  it("keeps its title and describes what it answers", () => {
    expect(metadata.title).toBe("Rulebook | F1 AI");
    expect(metadata.description).toContain("the stewards' decisions that applied them");
  });
});
