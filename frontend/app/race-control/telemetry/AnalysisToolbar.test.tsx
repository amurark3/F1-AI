import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AnalysisToolbar, type AnalysisToolbarProps } from "./AnalysisToolbar";
import { SESSIONS } from "./telemetryTestData";

function renderToolbar(props: Partial<AnalysisToolbarProps> = {}) {
  const onTab = vi.fn();
  const onSession = vi.fn();
  render(
    <AnalysisToolbar
      tab="map"
      onTab={onTab}
      sessions={SESSIONS}
      session="Q"
      allowed={() => true}
      onSession={onSession}
      {...props}
    >
      <span>per-view picker</span>
    </AnalysisToolbar>,
  );
  return { onTab, onSession };
}

describe("AnalysisToolbar", () => {
  it("holds the view switch, then the sessions, then the view's own pickers", () => {
    renderToolbar();
    const tabs = screen.getByRole("tablist", { name: "Analysis" });
    expect(screen.getByRole("tab", { name: "Speed Map" })).toHaveAttribute("aria-selected", "true");
    const sessions = screen.getByRole("radiogroup", { name: "Session" });
    expect(screen.getByRole("radio", { name: "Qualifying" })).toBeChecked();
    expect(tabs.compareDocumentPosition(sessions) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(sessions.compareDocumentPosition(screen.getByText("per-view picker"))).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  it("reports a chosen view and a chosen session, and keeps unstarted sessions disabled", async () => {
    const { onTab, onSession } = renderToolbar();
    expect(screen.getByRole("radio", { name: "Race" })).toBeDisabled();
    await userEvent.click(screen.getByRole("tab", { name: "Head-to-Head" }));
    expect(onTab).toHaveBeenCalledWith("head-to-head");
    await userEvent.click(screen.getByRole("radio", { name: "Practice 1" }));
    expect(onSession).toHaveBeenCalledWith("FP1");
  });

  it("leaves out sessions the view cannot show", () => {
    renderToolbar({ allowed: (code) => code === "R", session: null });
    expect(screen.getAllByRole("radio")).toHaveLength(1);
    expect(screen.getByRole("radio", { name: "Race" })).not.toBeChecked();
  });

  it("says so when the weekend has no session of this kind, and shows no session control before they are known", () => {
    const { unmount } = render(
      <AnalysisToolbar
        tab="tyres"
        onTab={vi.fn()}
        sessions={[]}
        session={null}
        allowed={() => false}
        onSession={vi.fn()}
      />,
    );
    expect(screen.getByText("No session of this kind on this weekend.")).toBeInTheDocument();
    unmount();
    render(
      <AnalysisToolbar
        tab="map"
        onTab={vi.fn()}
        sessions={null}
        session={null}
        allowed={() => true}
        onSession={vi.fn()}
      />,
    );
    expect(screen.queryByText(/No session/)).not.toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: "Session" })).not.toBeInTheDocument();
  });
});
