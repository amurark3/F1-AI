import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { StandingsFreshness } from "@/app/lib/standingsFreshness";
import { TEAMS_2026 } from "@/test/fixtures";

import { SourceBadge } from "./SourceBadge";

/** The morning after a race: f1db still on round 18, round 19 from OpenF1, Jolpica pre-penalty. */
const PROVISIONAL: StandingsFreshness = {
  as_of_round: 19,
  provisional: true,
  sources: [
    { source: "f1db", role: "base", through_round: 18, version: "v2026.18.0" },
    { source: "openf1-session-result", role: "points", round: 19, sessions: ["R"] },
    { source: "jolpica-standings", role: "cross_check", round: 19, status: "disagrees" },
  ],
};

/** "Nov 3, 01:46 UTC" in whatever zone the test machine runs in. */
const STAMP = String.raw`[A-Z][a-z]{2} \d{1,2}, \d{2}:\d{2}`;

describe("SourceBadge", () => {
  it("labels a confirmed table, its time and its sources", () => {
    render(<SourceBadge freshness={TEAMS_2026} asOf={TEAMS_2026.generated_at} />);

    const badge = screen.getByRole("button", { name: new RegExp(`^after round 19 · confirmed · as of ${STAMP}`) });
    expect(badge).toHaveAccessibleDescription("Sources Base: f1db v2026.19.0, through round 19");
    expect(badge).toHaveAttribute("data-status", "confirmed");
    expect(badge).toHaveClass("text-rc-ink-3");
    expect(badge).not.toHaveClass("border-dashed");
    expect(screen.queryByText("cross-check differs")).not.toBeInTheDocument();
  });

  it("sets a provisional table apart and flags a cross-check that disagrees", () => {
    render(<SourceBadge freshness={PROVISIONAL} />);

    const badge = screen.getByRole("button", { name: "after round 19 · provisional · cross-check differs" });
    expect(badge).toHaveAttribute("data-status", "provisional");
    expect(badge).toHaveClass("border-dashed", "text-rc-ink");
    expect(screen.getByText("cross-check differs")).toHaveClass("text-rc-red-text");
    expect(badge).toHaveAccessibleDescription(
      "Sources Base: f1db v2026.18.0, through round 18 " +
        "Points: OpenF1 session results, round 19 (race) " +
        "Cross-check: Jolpica standings, round 19 — disagrees",
    );
    expect(screen.getByText("Cross-check: Jolpica standings, round 19 — disagrees")).toHaveClass("text-rc-red-text");
    expect(screen.getByText("Base: f1db v2026.18.0, through round 18")).not.toHaveClass("text-rc-red-text");
  });

  it("shows only the time for a payload without a round, as plain text when it cites no sources", () => {
    const { container } = render(<SourceBadge asOf="2026-11-03T01:46:28Z" className="ml-2" />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    const badge = container.firstElementChild;
    expect(badge?.textContent).toMatch(new RegExp(`^as of ${STAMP}`));
    expect(badge).toHaveClass("ml-2", "text-rc-ink-3");
    expect(badge).not.toHaveAttribute("data-status");
  });

  it("shows the label without a tooltip when the payload lists no sources", () => {
    render(<SourceBadge freshness={{ as_of_round: 4, provisional: true }} />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText("after round 4 · provisional")).toHaveAttribute("data-status", "provisional");
  });

  it.each([
    ["no payload", null],
    ["a table before any round has points", { as_of_round: null, provisional: false, sources: [] }],
  ])("renders nothing for %s and no time", (_case, freshness) => {
    const { container } = render(<SourceBadge freshness={freshness} asOf={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("opens the source list on keyboard focus", async () => {
    const user = userEvent.setup();
    render(<SourceBadge freshness={PROVISIONAL} />);

    await user.tab();
    expect(screen.getByRole("button")).toHaveFocus();
    const list = screen.getByRole("tooltip");
    expect(list).toHaveAttribute("data-state", "open");
    expect(list).toHaveTextContent("Points: OpenF1 session results, round 19 (race)");
  });
});
