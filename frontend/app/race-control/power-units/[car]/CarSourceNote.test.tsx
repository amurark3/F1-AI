import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { POWER_UNITS_2026 } from "@/test/fixtures";
import { renderCar } from "@/test/renderCar";

import { CarSourceNote } from "./CarSourceNote";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

beforeEach(() => {
  vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
});

describe("CarSourceNote", () => {
  it("gives the source line with its times, and the allocations with their documents", async () => {
    const { container } = await renderCar(CarSourceNote, POWER_UNITS_2026);

    const lines = container.querySelectorAll("footer > p");
    expect(lines[0]).toHaveTextContent(
      "checked hourly · last checked 18 Nov 2026, 14:36 UTC · last change 08 Nov 2026, 19:41 UTC",
    );
    expect(lines[1]).toHaveTextContent(
      "Allocations as the FIA states them: ICE 4 · TC 4 · ES 3 · PU-CE 3 (FIA doc 55, 8 Nov ↗) · EXH 4 · MGU-K 3 · PU-ANC 6 (FIA doc 42, 8 Nov ↗)",
    );
    expect(screen.getByRole("link", { name: "FIA doc 55, 8 Nov ↗" })).toHaveAttribute("target", "_blank");
    expect(container.querySelector("ul")).toBeNull();
  });

  it("lists the page's notes and the car's own warnings", async () => {
    const changed = structuredClone(POWER_UNITS_2026);
    changed.freshness = { ...changed.freshness!, stale: true, error: "fia.com timed out" };
    changed.cars.find((c) => c.car_number === 6)!.warnings = ["Counts differ."];
    await renderCar(CarSourceNote, changed);

    expect(screen.getByText(/^Collection overdue · last checked .* · fia\.com timed out$/)).toBeInTheDocument();
    expect(screen.getByText("Counts differ.")).toBeInTheDocument();
  });

  it("names allocations that are pinned by hand or not stated, without a document", async () => {
    const changed = structuredClone(POWER_UNITS_2026);
    changed.elements![0].allowance_source = {
      ...changed.elements![0].allowance_source!,
      kind: "manual",
      note: "FIA said so",
    };
    changed.elements![1].allowance = null;
    changed.elements![1].allowance_source = null;
    const { container } = await renderCar(CarSourceNote, changed);

    expect(container.querySelectorAll("footer > p")[1]).toHaveTextContent("ICE 4 · TC ?");
    expect(screen.getByText("ICE: allowance pinned by hand (FIA said so)")).toBeInTheDocument();
    expect(screen.getByText("TC: allowance not stated by the FIA yet")).toBeInTheDocument();
  });

  it("leaves out the allocation line when there are no elements, and the document name when there is no link", async () => {
    const changed = structuredClone(POWER_UNITS_2026);
    changed.elements = [
      { ...changed.elements![0], allowance_source: { ...changed.elements![0].allowance_source!, url: null } },
    ];
    const { container } = await renderCar(CarSourceNote, changed);

    expect(container.querySelectorAll("footer > p")[1]).toHaveTextContent("ICE 4 (FIA doc 55, 8 Nov)");
    expect(screen.queryByRole("link", { name: /FIA doc 55/ })).not.toBeInTheDocument();
  });

  it("has no allocation line without elements", async () => {
    const { container } = await renderCar(CarSourceNote, { ...POWER_UNITS_2026, elements: undefined });

    expect(container.querySelectorAll("footer > p")).toHaveLength(1);
  });

  it("renders nothing for an unknown car, an uncollected season or an error", async () => {
    const unknown = await renderCar(CarSourceNote, POWER_UNITS_2026, { segment: "99" });
    expect(unknown.container.querySelector("footer")).toBeNull();
    unknown.unmount();

    const none = await renderCar(CarSourceNote, { ...POWER_UNITS_2026, available: false, cars: [] });
    expect(none.container.querySelector("footer")).toBeNull();
    none.unmount();

    await renderCar(CarSourceNote, { error: "boom" });
    expect(await screen.findByText("Source note unavailable")).toBeInTheDocument();
  });
});
