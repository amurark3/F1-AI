import { fireEvent, render, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { cloneElement, isValidElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { PaceTooltip, PointTooltip, paceStyles } from "./DegradationCharts";
import { DEGRADATION } from "./telemetryTestData";
import { TyreDegPanel } from "./TyreDegPanel";

import type { DegradationResponse } from "./telemetryModel";
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

function renderPanel(data: DegradationResponse) {
  server.use(http.get(apiUrl("/api/analysis/2026/20/tyre-degradation"), () => HttpResponse.json(data)));
  return renderWithProviders(<TyreDegPanel year={2026} round={20} session="R" />);
}

const titles = () => screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent);

describe("TyreDegPanel", () => {
  it("draws four independent cards, each titled from the data", async () => {
    renderPanel(DEGRADATION);
    expect(await screen.findByRole("heading", { level: 2, name: /^Lap times rose about 0.08 s/ })).toBeInTheDocument();
    expect(titles()).toEqual([
      "Lap times rose about 0.08 s per lap of tyre age",
      "ANT had the quickest final stint",
      "ANT's medium stint wore fastest",
      "VER did not stop; ANT and RUS stopped once",
    ]);
    expect(screen.getByText("Two laps had no tyre age.")).toBeInTheDocument();
    expect(screen.getByText(/Fuel correction assumes 70 kg/)).toBeInTheDocument();
  });

  it("shows each wear rate with its raw value beside it, then the raw rate alone when uncorrected", async () => {
    renderPanel(DEGRADATION);
    const wear = await screen.findByRole("list", { name: "Wear rate by stint" });
    const rows = within(wear).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("Kimi Antonelli");
    expect(rows[0]).toHaveTextContent("+0.130 s/lap");
    expect(rows[0]).toHaveTextContent("raw +0.100");
    fireEvent.click(screen.getByRole("checkbox", { name: "Fuel-corrected times (modelled)" }));
    const raw = within(screen.getByRole("list", { name: "Wear rate by stint" })).getAllByRole("listitem");
    expect(raw).toHaveLength(4);
    expect(raw[0]).toHaveTextContent("+0.100 s/lap");
    expect(raw[0]).not.toHaveTextContent("raw");
  });

  it("draws every stint with its laps and a compound key", async () => {
    renderPanel(DEGRADATION);
    const lengths = await screen.findByRole("list", { name: "Laps on each set" });
    expect(within(lengths).getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getByTitle("Hard · laps 7–10")).toHaveTextContent("4");
  });

  it("re-titles from the drivers picked and the left-out toggle", async () => {
    renderPanel(DEGRADATION);
    await screen.findByRole("heading", { level: 2, name: /^Lap times/ });
    fireEvent.click(screen.getByRole("button", { name: /ANT/ }));
    fireEvent.click(screen.getByRole("button", { name: /VER/ }));
    expect(titles()).toEqual([
      "Lap times rose about 0.04 s per lap of tyre age",
      "Race pace",
      "RUS's hard stint wore fastest",
      "RUS stopped once",
    ]);
    fireEvent.click(screen.getByRole("button", { name: /ANT/ }));
    expect(titles()[3]).toBe("ANT and RUS stopped once");
    fireEvent.click(screen.getByRole("button", { name: /ANT/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Show laps left out of the fit" }));
    expect(screen.queryByText("Left out of the fit")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /RUS/ }));
    expect(titles()).toEqual(["Lap time against tyre age", "Race pace", "Wear rate by stint", "Stint lengths"]);
    expect(screen.getByText("Pick a driver with clean laps to plot.")).toBeInTheDocument();
    expect(screen.getByText("Pick a driver with timed laps to plot.")).toBeInTheDocument();
    expect(screen.getByText(/No stint of the selected drivers/)).toBeInTheDocument();
    expect(screen.getByText("No stints for the selected drivers.")).toBeInTheDocument();
  });

  it("treats a race without a fuel model as raw times only", async () => {
    const stints = DEGRADATION.stints!.map((stint) =>
      stint.fit ? { ...stint, fit: { ...stint.fit, raw: { ...stint.fit.raw, slope: -0.01 } } } : stint,
    );
    renderPanel({
      ...DEGRADATION,
      stints,
      status_labels: undefined,
      neutralised: undefined,
      assumptions: { ...DEGRADATION.assumptions!, fuel: null },
    });
    await screen.findByRole("heading", { level: 2, name: /^Lap times/ });
    expect(screen.queryByRole("checkbox", { name: /Fuel-corrected/ })).not.toBeInTheDocument();
    expect(screen.getByText(/These laps are not fuel-corrected/)).toBeInTheDocument();
    expect(screen.getAllByText("-0.010 s/lap").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { level: 2, name: /fell about 0.01 s/ })).toBeInTheDocument();
  });

  it("falls back to neutral titles for a bare answer", async () => {
    renderPanel({ available: true, pending: false });
    expect(await screen.findByRole("heading", { level: 2, name: "Lap time against tyre age" })).toBeInTheDocument();
    expect(titles()).toEqual(["Lap time against tyre age", "Race pace", "Wear rate by stint", "Stint lengths"]);
  });

  it("explains an unavailable race", async () => {
    renderPanel({ available: false, pending: false, message: "No laps yet." });
    expect(await screen.findByText(/No laps yet/)).toBeInTheDocument();
  });
});

describe("tyre chart tooltips", () => {
  const point = { x: 3, y: 90.5, driver: "ANT", lap: 4, compound: "MEDIUM", status: "clean" };

  it("names the lap, the set and whether it was fitted", () => {
    const { rerender } = render(<PointTooltip active payload={[{ payload: point }]} labels={{}} />);
    expect(screen.getByText("ANT · lap 4 · Medium")).toBeInTheDocument();
    expect(screen.getByText("Fitted")).toBeInTheDocument();
    rerender(<PointTooltip active payload={[{ payload: { ...point, status: "sc" } }]} labels={{ sc: "Safety car" }} />);
    expect(screen.getByText("Left out: Safety car")).toBeInTheDocument();
    rerender(<PointTooltip active payload={[{ payload: { ...point, status: "odd" } }]} labels={{}} />);
    expect(screen.getByText("Left out: odd")).toBeInTheDocument();
    rerender(<PointTooltip payload={[{ payload: point }]} labels={{}} />);
    expect(screen.queryByText("Fitted")).not.toBeInTheDocument();
  });

  it("lists each driver's time on the lap, or a dash for a gap", () => {
    const { rerender } = render(
      <PaceTooltip
        active
        label={7}
        payload={[{ dataKey: "ANT", value: 90.5 }, { dataKey: "RUS", value: null }, { dataKey: "VER" }]}
      />,
    );
    expect(screen.getByText("Lap 7")).toBeInTheDocument();
    expect(screen.getByText("ANT 1:30.500")).toBeInTheDocument();
    expect(screen.getAllByText(/^(RUS|VER) -$/)).toHaveLength(2);
    rerender(<PaceTooltip active payload={[]} />);
    expect(screen.queryByText("Lap 7")).not.toBeInTheDocument();
  });

  it("dashes the second car of a team", () => {
    const [first, second] = paceStyles(DEGRADATION.drivers!);
    expect([first.dashed, second.dashed]).toEqual([false, true]);
  });
});
