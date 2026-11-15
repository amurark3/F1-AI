import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import fixture from "@/test/fixtures/qualifying-laps-mexico-2026.json";

import { DriverPicker, LapPicker, SegmentPicker } from "./AnalysisPickers";
import { LAPS } from "./telemetryTestData";

import type { LapListResponse } from "./telemetryModel";

const MEXICO = (fixture as unknown as LapListResponse).drivers!;
const LABELS = ["Q1", "Q2", "Q3"];

describe("AnalysisPickers", () => {
  it("asks for a driver when none is chosen, and marks one with no valid lap", () => {
    render(<DriverPicker label="Driver" drivers={LAPS.drivers!} value={null} onChange={vi.fn()} />);
    expect(screen.getByRole("option", { name: "Choose a driver" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /RUS · .* · no valid lap/ })).toBeInTheDocument();
  });

  it("draws nothing for a lap picker without a driver", () => {
    const { container } = render(<LapPicker driver={undefined} value={null} onChange={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("groups the drivers by how far they got, with their best in the part or why none", () => {
    render(
      <DriverPicker
        label="Driver"
        drivers={MEXICO}
        value="HAM"
        onChange={vi.fn()}
        segments={{ labels: LABELS, segment: 3 }}
      />,
    );
    const groups = screen.getAllByRole("group").map((group) => [group.getAttribute("label"), group.children.length]);
    expect(groups).toEqual([
      ["Q3", 9],
      ["Out in Q2", 6],
      ["Out in Q1", 6],
      ["Disqualified", 1],
    ]);
    expect(screen.getByRole("option", { name: /HAM · Ferrari · 1:16\.514/ })).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: /HUL · .* · didn't reach Q3 · P10 after Lawson's DSQ/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /LAW · .* · 1:17\.029/ })).toBeInTheDocument();
  });

  it("says no time set when the driver ran the part", () => {
    const ghost = { ...MEXICO[0], code: "GHO", segment_bests: [null, null, null], segment_reached: 3 };
    render(
      <DriverPicker
        label="Driver"
        drivers={[ghost]}
        value="GHO"
        onChange={vi.fn()}
        segments={{ labels: LABELS, segment: 3 }}
      />,
    );
    expect(screen.getByRole("option", { name: /GHO · .* · no time set in Q3/ })).toBeInTheDocument();
  });

  it("groups a driver's laps under the parts and names the part in the default option", () => {
    render(<LapPicker driver={MEXICO[0]} value={null} onChange={vi.fn()} segments={{ labels: LABELS, segment: 3 }} />);
    expect(screen.getAllByRole("group").map((group) => group.getAttribute("label"))).toEqual(LABELS);
    expect(screen.getByRole("option", { name: "Q3 · fastest valid lap" })).toBeInTheDocument();
  });

  it("offers Q1 to Q3 and reports a pick, or shows the notice when the parts are not published", async () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <SegmentPicker choice={{ labels: LABELS, segment: 3 }} notice={null} onChange={onChange} />,
    );
    await userEvent.click(screen.getByRole("radio", { name: "Q1" }));
    expect(onChange).toHaveBeenCalledWith(1);
    rerender(<SegmentPicker choice={null} notice="Q1/Q2/Q3 not published for this session" onChange={onChange} />);
    expect(screen.getByText("Q1/Q2/Q3 not published for this session")).toBeInTheDocument();
    rerender(<SegmentPicker choice={null} notice={undefined} onChange={onChange} />);
    expect(screen.queryByText(/not published/)).not.toBeInTheDocument();
  });
});
