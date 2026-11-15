import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RACE_RESULTS_2026 } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";

import { ChangedAfterFlagPanel, DebriefLinkPanel, FastestLapPanel } from "./ResultsSidePanels";

const MEXICO = RACE_RESULTS_2026.mexicoCity.race!;

describe("ChangedAfterFlagPanel", () => {
  it("lists each penalised car's road place, classified place and penalty, with who moved up", () => {
    renderWithProviders(<ChangedAfterFlagPanel changes={MEXICO.changed_after_flag} year={2026} />);

    expect(screen.getByText("Changed after the flag")).toBeInTheDocument();
    expect(screen.getByText("P7 → P13")).toBeInTheDocument();
    expect(screen.getByText("P10 → P17")).toBeInTheDocument();
    expect(screen.getByText("+30 s")).toBeInTheDocument();
    expect(screen.getAllByText(/^Moved up:/)[0]).toHaveTextContent("Liam Lawson 9 → 7");
  });

  it("says nothing when no penalty moved a car, and omits an empty moved-up line", () => {
    const { container, rerender } = renderWithProviders(<ChangedAfterFlagPanel changes={[]} year={2026} />);
    expect(container).toBeEmptyDOMElement();

    rerender(<ChangedAfterFlagPanel changes={[{ ...MEXICO.changed_after_flag[0], moved_up: [] }]} year={2026} />);
    expect(screen.queryByText(/^Moved up:/)).not.toBeInTheDocument();
  });
});

describe("FastestLapPanel", () => {
  it("shows the lap time in the fastest-overall colour with who set it and on which lap", () => {
    renderWithProviders(<FastestLapPanel lap={MEXICO.fastest_lap} year={2026} />);

    expect(screen.getByText("1:19.268")).toHaveClass("text-(--f1-sector-best)");
    expect(screen.getByText(/lap 50/)).toBeInTheDocument();
  });

  it("is absent when no fastest lap is known", () => {
    const { container } = renderWithProviders(<FastestLapPanel lap={null} year={2026} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("DebriefLinkPanel", () => {
  it("links to the debrief", () => {
    renderWithProviders(<DebriefLinkPanel />);
    expect(screen.getByRole("link", { name: "Read the debrief" })).toHaveAttribute("href", "/race-control/debriefs");
  });
});
