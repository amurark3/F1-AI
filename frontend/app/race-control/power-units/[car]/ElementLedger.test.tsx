import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { POWER_UNITS_2026 } from "@/test/fixtures";
import { renderCar } from "@/test/renderCar";

import { ElementLedger } from "./ElementLedger";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

beforeEach(() => {
  vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
});

function tile(name: RegExp): HTMLElement {
  return screen.getByRole("button", { name });
}

describe("ElementLedger for car 6", () => {
  it("titles the ledger and presses the newest unit, with its ruling", async () => {
    await renderCar(ElementLedger, POWER_UNITS_2026);

    expect(screen.getByRole("heading", { level: 2, name: "Elements" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 3, name: "All seven elements past the allocation" }),
    ).toBeInTheDocument();
    expect(tile(/^ICE unit 8, beyond/)).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("ICE #8 · 4th beyond the 4 allowed")).toBeInTheDocument();
    expect(screen.getByText("Introduced at the Singapore GP (named in an FIA document).")).toBeInTheDocument();
    expect(screen.getByText("Stewards: Pit-lane start, first used in Qualifying.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "That weekend ↓" })).toHaveAttribute("href", "#round-17");
    expect(screen.getAllByText(/8 used \/ 4 allowed/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("+4").length).toBeGreaterThan(0);
  });

  it("moves the selection and the inspector when another tile is pressed", async () => {
    const { user } = await renderCar(ElementLedger, POWER_UNITS_2026);

    await user.click(tile(/^ICE unit 1, within/));

    expect(tile(/^ICE unit 1, within/)).toHaveAttribute("aria-pressed", "true");
    expect(tile(/^ICE unit 8, beyond/)).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText("ICE #1 · within the 4 allowed")).toBeInTheDocument();
    expect(screen.getByText(/the only round between two FIA usage reports\)\./)).toBeInTheDocument();
    expect(screen.getByText("No penalty: within the season's allocation.")).toBeInTheDocument();
  });

  it("lists the legend", async () => {
    await renderCar(ElementLedger, POWER_UNITS_2026);

    const legend = screen.getByRole("list", { name: "Legend" });
    expect(legend).toHaveTextContent("Within the allocation");
    expect(legend).toHaveTextContent("No longer counted by the FIA");
  });
});

describe("ElementLedger states", () => {
  it("car 12: a spare box, the uncounted unit struck, and its own ruling", async () => {
    const { user } = await renderCar(ElementLedger, POWER_UNITS_2026, { segment: "12" });

    expect(screen.getAllByText(/3 used \/ 4 allowed/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("spare").length).toBeGreaterThan(0);
    expect(screen.getByText("Not counted")).toBeInTheDocument();
    await user.click(tile(/^EXH unit 4, within the allocation, not counted/));
    expect(screen.getByText("EXH #4 · not counted")).toBeInTheDocument();
    expect(screen.getByText(/from round 13, so it is not in the total\./)).toBeInTheDocument();
  });

  it("car 12 opens on its newest unit", async () => {
    await renderCar(ElementLedger, POWER_UNITS_2026, { segment: "12" });

    expect(screen.getByText("PU-ANC #6 · within the 6 allowed")).toBeInTheDocument();
    expect(screen.getByText("No penalty: within the season's allocation.")).toBeInTheDocument();
  });

  it("car 18: units whose round is not pinned down, with no jump link", async () => {
    const { user } = await renderCar(ElementLedger, POWER_UNITS_2026, { segment: "18" });

    await user.click(tile(/^ICE unit 6, beyond/));
    expect(screen.getByText("ICE #6 · 2nd beyond the 4 allowed")).toBeInTheDocument();
    expect(screen.getByText(/Introduced between round 18 and round 19/)).toBeInTheDocument();
    expect(screen.getByText(/No stewards' decision can be matched to this unit/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "That weekend ↓" })).not.toBeInTheDocument();
  });

  it("shows an element with no stated allowance as '?'", async () => {
    const changed = structuredClone(POWER_UNITS_2026);
    changed.cars.find((c) => c.car_number === 12)!.elements[0].allowance = null;
    await renderCar(ElementLedger, changed, { segment: "12" });

    expect(screen.getAllByText(/\? allowed/).length).toBeGreaterThan(0);
  });

  it("names an element by its code when the payload lists no element names", async () => {
    await renderCar(ElementLedger, { ...POWER_UNITS_2026, elements: undefined }, { segment: "12" });

    expect(screen.getAllByText("ICE").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/\? allowed|4 allowed/).length).toBeGreaterThan(0);
  });

  it("does not offer the jump when the weekend has no event", async () => {
    const changed = structuredClone(POWER_UNITS_2026);
    const six = changed.cars.find((c) => c.car_number === 6)!;
    six.events = six.events.filter((e) => e.round !== 17);
    await renderCar(ElementLedger, changed);

    expect(screen.queryByRole("link", { name: "That weekend ↓" })).not.toBeInTheDocument();
  });

  it("renders nothing for an unknown car or an uncollected season", async () => {
    const unknown = await renderCar(ElementLedger, POWER_UNITS_2026, { segment: "99" });
    expect(unknown.container).toBeEmptyDOMElement();
    unknown.unmount();

    const none = await renderCar(ElementLedger, { ...POWER_UNITS_2026, available: false, cars: [] });
    expect(none.container).toBeEmptyDOMElement();
  });

  it("keeps its head over a failure card for an error payload", async () => {
    await renderCar(ElementLedger, { error: "boom" });

    expect(await screen.findByText("Element ledger unavailable")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Elements" })).toBeInTheDocument();
  });

  it("copes with a car that has no units at all", async () => {
    const changed = structuredClone(POWER_UNITS_2026);
    changed.cars.find((c) => c.car_number === 12)!.elements = [];
    await renderCar(ElementLedger, changed, { segment: "12" });

    expect(screen.getByRole("heading", { level: 3, name: "Every element within the allocation" })).toBeInTheDocument();
  });
});
