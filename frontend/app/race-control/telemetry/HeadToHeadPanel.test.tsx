import { fireEvent, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { cloneElement, isValidElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { DIRECTORY_2026 } from "@/test/fixtures";
import mexicoLaps from "@/test/fixtures/qualifying-laps-mexico-2026.json";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { HeadToHeadControls } from "./HeadToHeadControls";
import { HeadToHeadPanel } from "./HeadToHeadPanel";
import { COMPARISON, LAPS } from "./telemetryTestData";
import { TraceTooltip } from "./TelemetryTraces";

import type { ComparisonResponse, LapListDriver, LapListResponse } from "./telemetryModel";
import type * as Recharts from "recharts";

// jsdom has no layout, so the responsive wrapper would measure 0 x 0: give the chart a size.
vi.mock("recharts", async (importOriginal) => {
  const recharts = await importOriginal<typeof Recharts>();
  return {
    ...recharts,
    ResponsiveContainer: ({ children }: { children: ReactNode }) =>
      isValidElement<{ width?: number; height?: number }>(children)
        ? cloneElement(children, { width: 480, height: 200 })
        : null,
  };
});

const TWO_DRIVERS: LapListResponse & { drivers: LapListDriver[] } = {
  ...LAPS,
  drivers: [
    ...LAPS.drivers!,
    { ...LAPS.drivers![1], code: "VER", number: 1, name: "Max Verstappen", team: "Red Bull Racing" },
  ],
};

function serve(compare: ComparisonResponse, laps: LapListResponse = TWO_DRIVERS) {
  server.use(
    http.get(apiUrl("/api/profiles/2026/directory"), () => HttpResponse.json(DIRECTORY_2026)),
    http.get(apiUrl("/api/analysis/2026/20/laps"), () => HttpResponse.json(laps)),
    http.get(apiUrl("/api/analysis/2026/20/compare"), () => HttpResponse.json(compare)),
  );
}

function renderPanel(compare: ComparisonResponse) {
  serve(compare);
  return renderWithProviders(<HeadToHeadPanel year={2026} round={20} session="Q" a={null} b={null} segment={null} />);
}

// jsdom lays nothing out: stub the transform the map reads the pointer through.
function stubPointer() {
  vi.stubGlobal(
    "DOMPoint",
    class {
      constructor(
        readonly x: number,
        readonly y: number,
      ) {}
      matrixTransform() {
        return { x: this.x, y: this.y };
      }
    },
  );
  Object.defineProperty(SVGSVGElement.prototype, "getScreenCTM", {
    configurable: true,
    value: () => ({ inverse: () => ({}) }),
  });
}

function unstubPointer() {
  vi.unstubAllGlobals();
  Reflect.deleteProperty(SVGSVGElement.prototype, "getScreenCTM");
}

describe("HeadToHeadPanel", () => {
  it("draws independent cards, each titled from the data", async () => {
    renderPanel(COMPARISON);
    expect(await screen.findByRole("heading", { level: 2, name: "ANT by 0.270 s" })).toBeInTheDocument();
    const titles = screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent);
    expect(titles).toEqual([
      "ANT by 0.270 s",
      "ANT faster in 2 of 2 mini-sectors, RUS in 0",
      "ANT gains 0.14 s between 0.0 and 1.0 km",
      "Top speed 320 km/h for ANT, 310 for RUS",
      "Both flat out for 77% of the lap",
      expect.stringMatching(/^RUS on the brakes/),
      expect.stringMatching(/^ANT in gear 8/),
    ]);
    expect(screen.getByText("Sector 2")).toBeInTheDocument();
    expect(screen.getAllByText("level")).toHaveLength(2);
    expect(screen.getByText("RUS +0.100")).toBeInTheDocument();
    expect(screen.getByText("ANT +0.100")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Mini-sector winner" })).toBeInTheDocument();
    expect(screen.getAllByRole("list", { name: "Drivers" })).toHaveLength(4);
    expect(screen.getByText("One sample was missing.")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /faster in each of 2 mini-sectors/ })).toBeInTheDocument();
  });

  it("falls back to neutral titles and skips the map when the answer is bare", async () => {
    renderPanel({ available: true, pending: false });
    expect(await screen.findByRole("heading", { level: 2, name: "Lap and sector times" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Gap along the lap" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Speed trace" })).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("reads out the mini-sector under the pointer, or a dash outside any", async () => {
    stubPointer();
    renderPanel({
      ...COMPARISON,
      mini_sectors: [{ label: "Mini-sector 1", start: 0, end: 500, gain: 0.1, faster: "a" }],
    });
    const map = await screen.findByRole("img");
    fireEvent.mouseMove(map, { clientX: 1000, clientY: 0 });
    expect(screen.getByText("500 m · Mini-sector 1 · ANT +0.100s")).toBeInTheDocument();
    fireEvent.mouseMove(map, { clientX: 0, clientY: 0 });
    expect(screen.getByText("0 m · Mini-sector 1 · ANT +0.100s")).toBeInTheDocument();
    unstubPointer();
  });

  it("reads a dash on the map when the answer has no mini-sectors", async () => {
    stubPointer();
    renderPanel({ ...COMPARISON, mini_sectors: undefined });
    fireEvent.mouseMove(await screen.findByRole("img"), { clientX: 1000, clientY: 0 });
    expect(screen.getByText("500 m · -")).toBeInTheDocument();
    unstubPointer();
  });

  it("explains an unavailable comparison", async () => {
    renderPanel({ available: false, pending: false, reason: "no_telemetry", message: "No car data." });
    expect(await screen.findByText("No car data.")).toBeInTheDocument();
  });
});

describe("TraceTooltip", () => {
  const row = { ...{ distance: 700, delta: 0.1, speed_a: 200, speed_b: 190, brake_a: 100, brake_b: 0 } } as never;
  const codes = { a: "ANT", b: "RUS" };

  it("reads both drivers' values, with on/off for the brake", () => {
    const speed = { eyebrow: "", unit: "km/h", keys: ["speed_a", "speed_b"], height: 1, title: () => "" } as never;
    const brake = {
      eyebrow: "",
      unit: "",
      keys: ["brake_a", "brake_b"],
      height: 1,
      title: () => "",
      format: (value: number) => (value > 0 ? "on" : "off"),
    } as never;
    const { rerender } = render(<TraceTooltip active payload={[{ payload: row }]} spec={speed} codes={codes} />);
    expect(screen.getByText("ANT 200 km/h")).toBeInTheDocument();
    rerender(<TraceTooltip active payload={[{ payload: row }]} spec={brake} codes={codes} />);
    expect(screen.getByText("ANT on")).toBeInTheDocument();
    expect(screen.getByText("RUS off")).toBeInTheDocument();
  });

  it("reads the gap, and shows nothing when idle", () => {
    const { rerender, container } = render(
      <TraceTooltip active payload={[{ payload: row }]} spec={null} codes={codes} />,
    );
    expect(screen.getByText("RUS behind by 0.100s")).toBeInTheDocument();
    rerender(
      <TraceTooltip
        active
        payload={[{ payload: { ...(row as object), delta: -0.1 } as never }]}
        spec={null}
        codes={codes}
      />,
    );
    expect(screen.getByText("RUS ahead by 0.100s")).toBeInTheDocument();
    rerender(<TraceTooltip active={false} payload={[]} spec={null} codes={codes} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("HeadToHeadControls", () => {
  function renderControls(a: string | null, b: string | null, laps: LapListResponse = TWO_DRIVERS) {
    serve(COMPARISON, laps);
    const onPick = vi.fn();
    const view = renderWithProviders(
      <HeadToHeadControls
        year={2026}
        round={20}
        session="Q"
        a={a}
        b={b}
        segment={null}
        onPick={onPick}
        onSegment={vi.fn()}
      />,
    );
    return { ...view, onPick };
  }

  it("offers the two quickest drivers and reports a pick, swapping when both would match", async () => {
    const { user, onPick } = renderControls(null, null);
    const a = await screen.findByRole("combobox", { name: "Driver A" });
    const b = screen.getByRole("combobox", { name: "Driver B" });
    expect(a).toHaveValue("ANT");
    expect(b).toHaveValue("VER");
    await user.selectOptions(a, "VER");
    expect(onPick).toHaveBeenLastCalledWith("VER", "ANT");
    await user.selectOptions(b, "ANT");
    expect(onPick).toHaveBeenLastCalledWith("VER", "ANT");
    await user.selectOptions(b, "VER");
    expect(onPick).toHaveBeenCalledTimes(3);
  });

  it("passes the other pick through when the new one differs", async () => {
    const { user, onPick } = renderControls("ANT", "VER", {
      ...TWO_DRIVERS,
      drivers: [...TWO_DRIVERS.drivers, { ...TWO_DRIVERS.drivers[1], code: "NOR", number: 4 }],
    });
    await user.selectOptions(await screen.findByRole("combobox", { name: "Driver A" }), "NOR");
    expect(onPick).toHaveBeenLastCalledWith("NOR", "VER");
    await user.selectOptions(screen.getByRole("combobox", { name: "Driver B" }), "NOR");
    expect(onPick).toHaveBeenLastCalledWith("ANT", "NOR");
  });

  it("renders nothing without two drivers who have a lap", async () => {
    const { container } = renderControls(null, null, LAPS);
    await new Promise((done) => setTimeout(done, 50));
    expect(container).toBeEmptyDOMElement();
  });
});

describe("head-to-head in qualifying", () => {
  function serveMexico() {
    const asked: URLSearchParams[] = [];
    server.use(
      http.get(apiUrl("/api/profiles/2026/directory"), () => HttpResponse.json(DIRECTORY_2026)),
      http.get(apiUrl("/api/analysis/2026/19/laps"), () => HttpResponse.json(mexicoLaps)),
      http.get(apiUrl("/api/analysis/2026/19/compare"), ({ request }) => {
        asked.push(new URL(request.url).searchParams);
        return HttpResponse.json(COMPARISON);
      }),
    );
    return asked;
  }

  it("compares the two quickest of the part and names it in the title", async () => {
    const asked = serveMexico();
    renderWithProviders(<HeadToHeadPanel year={2026} round={19} session="Q" a={null} b={null} segment={1} />);
    expect(await screen.findByRole("heading", { level: 2, name: "Q1 · ANT by 0.270 s" })).toBeInTheDocument();
    expect(asked[0].get("segment")).toBe("1");
  });

  it("defaults to the last part both drivers reached", async () => {
    const asked = serveMexico();
    renderWithProviders(<HeadToHeadPanel year={2026} round={19} session="Q" a="HAM" b="HUL" segment={null} />);
    expect(await screen.findByRole("heading", { level: 2, name: "Q2 · ANT by 0.270 s" })).toBeInTheDocument();
    expect(asked[0].get("segment")).toBe("2");
  });

  it("groups both pickers and says which part the laps are from", async () => {
    serveMexico();
    const { user } = renderWithProviders(
      <HeadToHeadControls
        year={2026}
        round={19}
        session="Q"
        a="HAM"
        b="HUL"
        segment={null}
        onPick={vi.fn()}
        onSegment={vi.fn()}
      />,
    );
    expect(await screen.findByText("Each driver's fastest valid lap in Q2")).toBeInTheDocument();
    expect(screen.getAllByRole("group", { name: "Out in Q1" })).toHaveLength(2);
    await user.click(screen.getByRole("radio", { name: "Q1" }));
  });
});
