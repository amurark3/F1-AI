import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PROFILE_PAGES_2026 } from "@/test/fixtures";

import { formGuide } from "./driverModel";
import { FormGuide } from "./FormGuide";

describe("FormGuide", () => {
  it("shows a win on gold, a podium on a gold edge and the rest plain, each with its sentence", () => {
    render(<FormGuide chips={formGuide(PROFILE_PAGES_2026.verstappen)} />);

    const chips = within(screen.getByRole("list", { name: "Last five races" })).getAllByRole("listitem");
    expect(chips).toHaveLength(5);
    expect(chips[0]).toHaveClass("bg-rc-gold", "text-background");
    expect(chips[2]).toHaveClass("border-rc-gold/50");
    expect(chips[0]).toHaveAttribute("title", expect.stringContaining("R16 Bahrain GP:"));
    expect(within(chips[0]).getByText(/^R16 Bahrain GP:/)).toHaveClass("sr-only");
  });

  it("draws a car that did not finish in red, by its code", () => {
    render(
      <FormGuide chips={[{ axis: "R9", text: "DNF", tone: "out", sentence: "R9 British GP: retired (Spun off)" }]} />,
    );

    expect(screen.getByText("DNF").closest("li")).toHaveClass("text-rc-red-text");
  });

  it("leaves an ordinary finish in the plain tone", () => {
    render(<FormGuide chips={formGuide(PROFILE_PAGES_2026.hamilton)} />);

    expect(screen.getByText("4").closest("li")).toHaveClass("border-rc-line");
  });
});
