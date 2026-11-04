import { render, screen } from "@testing-library/react";
import { useReducedMotion } from "framer-motion";
import { describe, expect, it, vi } from "vitest";

import { CIRCUIT_RECORDS, SAO_PAULO_2026 } from "@/test/fixtures";

import { CircuitStats } from "./CircuitStats";

import type * as FramerMotion from "framer-motion";

vi.mock("framer-motion", async (importOriginal) => ({
  ...(await importOriginal<typeof FramerMotion>()),
  useReducedMotion: vi.fn(),
}));

/** Each cell as "label: value (detail)". */
function readCells(): string[] {
  return screen.getAllByRole("term").map((term) => {
    const values = [];
    for (let node = term.nextElementSibling; node?.tagName === "DD"; node = node.nextElementSibling) {
      values.push(node.textContent);
    }
    const [value, detail] = values;
    return `${term.textContent}: ${value}${detail ? ` (${detail})` : ""}`;
  });
}

const { race, circuit } = SAO_PAULO_2026;

describe("CircuitStats", () => {
  it("lists Interlagos from f1db's record, with the lap record holder's f1db surname", () => {
    vi.mocked(useReducedMotion).mockReturnValue(true);
    render(<CircuitStats record={circuit.record} lapRecord={circuit.lap_record} basics={race.circuit ?? {}} />);

    expect(readCells()).toEqual([
      "Length: 4.309km",
      "Turns: 15",
      "Laps: 71",
      "Distance: 305.9km",
      "Direction: Anti-clockwise",
      "Lap record: 1:10.540 (Bottas · 2018)",
      "First GP: 1973",
      "GPs held here: 42",
    ]);
  });

  it("turns the direction icon the way the circuit runs", () => {
    vi.mocked(useReducedMotion).mockReturnValue(true);
    const { unmount } = render(<CircuitStats record={circuit.record} lapRecord={null} basics={{}} />);
    const anti = screen.getByText("Direction").querySelector("svg");
    expect(anti).toHaveClass("motion-safe:animate-wx-spin");
    expect(anti).toHaveStyle({ animationDirection: "reverse" });
    expect(screen.getByText("Length").querySelector("svg")).not.toHaveClass("motion-safe:animate-wx-spin");
    unmount();

    render(<CircuitStats record={CIRCUIT_RECORDS.mexicoCity2026} lapRecord={null} basics={{}} />);
    expect(screen.getByText("Clockwise")).toBeInTheDocument();
    expect(screen.getByText("Direction").querySelector("svg")).not.toHaveStyle({ animationDirection: "reverse" });
  });

  it("falls back to the schedule's facts while f1db's record is missing", () => {
    vi.mocked(useReducedMotion).mockReturnValue(true);
    render(<CircuitStats record={null} lapRecord={race.circuit?.lap_record ?? null} basics={race.circuit ?? {}} />);

    // The schedule's copy of the lap record carries no surname: the full name, never a split.
    expect(readCells()).toEqual([
      "Length: 4.309km",
      "Laps: 71",
      "Lap record: 1:10.540 (Valtteri Bottas · 2018)",
      "First GP: 1973",
    ]);
  });

  it("takes a new circuit's first year from the schedule, as f1db has no earlier race there", () => {
    vi.mocked(useReducedMotion).mockReturnValue(true);
    const { race: madring, record } = CIRCUIT_RECORDS.madring2026;
    render(<CircuitStats record={record} lapRecord={null} basics={{ first_gp: madring.circuit?.first_gp }} />);

    expect(readCells()).toEqual([
      "Length: 5.416km",
      "Turns: 22",
      "Laps: 57",
      "Distance: 308.5km",
      "Direction: Clockwise",
      "First GP: 2026",
      "GPs held here: 0",
    ]);
  });

  it("renders nothing when no source knows the circuit", () => {
    const { container } = render(<CircuitStats record={null} lapRecord={null} basics={{}} />);
    expect(container).toBeEmptyDOMElement();
  });
});
