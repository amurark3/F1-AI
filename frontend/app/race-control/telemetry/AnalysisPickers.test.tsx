import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DriverPicker, LapPicker } from "./AnalysisPickers";
import { LAPS } from "./telemetryTestData";

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
});
