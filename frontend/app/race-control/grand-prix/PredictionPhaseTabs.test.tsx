import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PREDICTION_REVIEW_R19 } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";

import { PredictionBar, type PhaseTabState } from "./PredictionPhaseTabs";

function states(changes: Array<Partial<PhaseTabState>> = [{}, {}]): PhaseTabState[] {
  return [
    {
      phase: "pre_qualifying",
      available: true,
      hasSnapshot: true,
      storedAt: "2026-10-30T10:00:00Z",
      ...changes[0],
    },
    {
      phase: "post_qualifying",
      available: true,
      hasSnapshot: true,
      storedAt: "2026-11-01T01:38:00Z",
      ...changes[1],
    },
  ];
}

function bar(tabs: PhaseTabState[], accuracy = PREDICTION_REVIEW_R19.accuracy) {
  return renderWithProviders(
    <PredictionBar states={tabs} activePhase="post_qualifying" onSelectPhase={vi.fn()} accuracy={accuracy} />,
  );
}

describe("PredictionBar", () => {
  it("shows the model's record over its last scored races", () => {
    bar(states());

    expect(screen.getByText(/Top-3 62% · 8 of last 8 scored/)).toBeVisible();
  });

  it("says when nothing has been scored yet", () => {
    bar(states(), { races_evaluated: 0 });

    expect(screen.getByText("not yet scored")).toBeVisible();
  });

  it("reads a record with no podium figure, window or error as dashes and the default window", () => {
    bar(states(), { races_evaluated: 2 });

    expect(screen.getByText(/Top-3 – · 2 of last 8 scored/)).toBeVisible();
    expect(screen.getByText(/Top-3/)).not.toHaveAttribute("title");
  });

  it("says what each phase holds: awaiting qualifying, not computed, stored", () => {
    bar(states([{ hasSnapshot: false }, { available: false, hasSnapshot: false }]));
    expect(screen.getByText("not computed")).toBeInTheDocument();
    expect(screen.getByText("awaiting qualifying")).toBeInTheDocument();
  });

  it("gives visitors no way to run the model: the only buttons pick a phase", () => {
    bar(states());

    expect(screen.queryByRole("button", { name: /run/i })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(2);
  });
});
