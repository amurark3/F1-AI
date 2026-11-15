import { fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DIRECTORY_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { LAPS, TRACK_MAP } from "./telemetryTestData";
import { TrackMapPanel } from "./TrackMapPanel";

import type { TrackMapResponse } from "./telemetryModel";

function renderPanel(map: TrackMapResponse, props: { driver?: string | null; lap?: number | null } = {}) {
  server.use(
    http.get(apiUrl("/api/profiles/2026/directory"), () => HttpResponse.json(DIRECTORY_2026)),
    http.get(apiUrl("/api/analysis/2026/20/laps"), () => HttpResponse.json(LAPS)),
    http.get(apiUrl("/api/analysis/2026/20/track-map"), () => HttpResponse.json(map)),
  );
  return renderWithProviders(
    <TrackMapPanel year={2026} round={20} session="Q" driver={props.driver ?? null} lap={props.lap ?? null} />,
  );
}

describe("TrackMapPanel", () => {
  it("titles the map from the data: driver, lap and lap time", async () => {
    renderPanel(TRACK_MAP);
    const title = await screen.findByRole("heading", { level: 2 });
    expect(title).toHaveTextContent(/Antonelli · lap 14 · 1:34\.035/);
    expect(screen.getByText(/Slow is deep blue, fast is pale/)).toBeInTheDocument();
    expect(screen.getAllByText("341 km/h")).toHaveLength(2);
    expect(screen.getByText("Lap 14 · fastest valid")).toBeInTheDocument();
    expect(screen.getByText("One sample was missing.")).toBeInTheDocument();
    expect(screen.getByText("150 m")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "ANT lap coloured by speed, 90 to 320 km/h" })).toBeInTheDocument();
  });

  it("marks a deleted lap and a missing speed trap", async () => {
    const lap = {
      ...TRACK_MAP.lap!,
      deleted: true,
      is_fastest: false,
      speed_traps: { i1: null, i2: null, speed_trap: null },
    };
    renderPanel({ ...TRACK_MAP, lap });
    expect(await screen.findByText("Lap 14 · deleted")).toBeInTheDocument();
    expect(screen.getByText("-", { selector: "p" })).toBeInTheDocument();
  });

  it("shows what it has when the answer carries no lap, stats, points, zones or driver", async () => {
    renderPanel({ available: true, pending: false });
    await waitFor(() => {
      expect(screen.queryByText(/Loading the lap/)).not.toBeInTheDocument();
    });
    expect(await screen.findByText("Speed map")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2 })).not.toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("still draws a lap whose driver is not named", async () => {
    renderPanel({ ...TRACK_MAP, driver: undefined });
    expect(await screen.findByRole("img", { name: /^lap coloured by speed/ })).toBeInTheDocument();
  });

  it("skips the peak marker when no top speed is known", async () => {
    renderPanel({ ...TRACK_MAP, stats: undefined, braking_zones: undefined });
    expect(await screen.findByRole("img")).toBeInTheDocument();
    expect(screen.queryByText("Top speed")).not.toBeInTheDocument();
  });

  it("explains an unavailable lap instead of drawing one", async () => {
    renderPanel({ available: false, pending: false, reason: "no_telemetry", message: "No car data for this lap." });
    expect(await screen.findByText("No car data for this lap.")).toBeInTheDocument();
  });
});

describe("TrackMap", () => {
  let matrix: DOMMatrix | null;

  beforeEach(() => {
    matrix = null;
    // jsdom lays nothing out, so it has no SVGSVGElement.getScreenCTM to spy on.
    Object.defineProperty(SVGSVGElement.prototype, "getScreenCTM", { configurable: true, value: () => matrix });
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
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    Reflect.deleteProperty(SVGSVGElement.prototype, "getScreenCTM");
  });

  it("reads out the sample under the pointer, and clears when it leaves", async () => {
    renderPanel(TRACK_MAP);
    const map = await screen.findByRole("img");
    expect(screen.getByText("Hover the track for a reading")).toBeInTheDocument();

    // No transform known yet: the pointer reads nothing.
    fireEvent.mouseMove(map, { clientX: 1000, clientY: 0 });
    expect(screen.getByText("Hover the track for a reading")).toBeInTheDocument();

    matrix = { inverse: () => ({}) } as unknown as DOMMatrix;
    fireEvent.mouseMove(map, { clientX: 1500, clientY: -800 });
    expect(screen.getByText("200 m · 90 km/h · gear 2 · throttle 0% · braking")).toBeInTheDocument();
    fireEvent.mouseMove(map, { clientX: 1000, clientY: 0 });
    expect(screen.getByText("100 m · 320 km/h · gear 8 · throttle 100%")).toBeInTheDocument();
    fireEvent.mouseLeave(map);
    expect(screen.getByText("Hover the track for a reading")).toBeInTheDocument();
  });

  it("draws itself in, behind motion-safe, by revealing the lap through a mask", async () => {
    renderPanel(TRACK_MAP);
    const map = await screen.findByRole("img");
    const reveal = map.querySelector("mask polyline");
    expect(reveal).toHaveClass("motion-safe:animate-track-draw");
    expect(reveal).toHaveAttribute("pathLength", "1");
    const group = map.querySelector("g[mask]");
    expect(group?.getAttribute("mask")).toBe(`url(#${map.querySelector("mask")?.id})`);
    expect(group?.querySelectorAll("line")).toHaveLength(3);
  });
});
