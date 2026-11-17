import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PROFILE_PAGES_2026 } from "@/test/fixtures";

import { TeamKpis } from "./TeamKpis";

describe("TeamKpis", () => {
  it("shows Mercedes' four figures with who earned them", () => {
    render(<TeamKpis profile={PROFILE_PAGES_2026.mercedes} />);

    expect(screen.getByText("Wins").parentElement).toHaveTextContent("12of 20Antonelli 9 · Russell 3");
    expect(screen.getByText("Podiums").parentElement).toHaveTextContent("24of 40 starts");
    expect(screen.getByText("Poles").parentElement).toHaveTextContent("12Antonelli 7 · Russell 5");
    expect(screen.getByText("Retirements").parentElement).toHaveTextContent("4Antonelli R7 · Russell R5, R10, R16");
  });
});
