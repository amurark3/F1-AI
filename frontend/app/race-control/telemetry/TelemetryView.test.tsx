import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { cloneElement, isValidElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, SEASON_2026 } from "@/test/fixtures";
import mexicoLaps from "@/test/fixtures/qualifying-laps-mexico-2026.json";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { COMPARISON, DEGRADATION, SESSIONS, TRACK_MAP } from "./telemetryTestData";
import { pickSession, TelemetryView, type TelemetrySeed } from "./TelemetryView";

import type { WeekendResponse } from "./telemetryModel";
import type * as Recharts from "recharts";

const nav = vi.hoisted(() => ({ search: "", replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(nav.search),
  useRouter: () => ({ replace: nav.replace }),
  usePathname: () => "/race-control/telemetry",
}));
vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));
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

const SEED: TelemetrySeed = { year: 2026, schedule: SEASON_2026.schedule };
const RACE_RUN = SESSIONS.map((session) => ({ ...session, started: true }));
const WEEKEND: WeekendResponse = { available: true, pending: false, sessions: SESSIONS };

function serve(weekend: WeekendResponse = WEEKEND) {
  server.use(
    http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
    http.get(apiUrl("/api/champions/2026"), () => HttpResponse.json(SEASON_2026.winners)),
    http.get(apiUrl("/api/schedule/:year"), () => HttpResponse.json(SEASON_2026.schedule)),
    http.get(apiUrl("/api/analysis/:year/:round/sessions"), () => HttpResponse.json(weekend)),
    http.get(apiUrl("/api/analysis/:year/:round/laps"), () => HttpResponse.json(mexicoLaps)),
    http.get(apiUrl("/api/analysis/:year/:round/track-map"), () => HttpResponse.json(TRACK_MAP)),
    http.get(apiUrl("/api/analysis/:year/:round/compare"), () => HttpResponse.json(COMPARISON)),
    http.get(apiUrl("/api/analysis/:year/:round/tyre-degradation"), () => HttpResponse.json(DEGRADATION)),
  );
}

function renderView(search: string, seed: TelemetrySeed = SEED) {
  nav.search = search;
  return renderWithProviders(<TelemetryView seed={seed} />);
}

/** The query the view last wrote to the URL. */
function lastQuery(): URLSearchParams {
  const url = String(nav.replace.mock.lastCall?.[0]);
  return new URLSearchParams(url.split("?")[1]);
}

describe("pickSession", () => {
  it("keeps the session asked for when the tab can show it and it has run", () => {
    expect(pickSession(RACE_RUN, "map", "FP1")).toBe("FP1");
  });

  it("falls back to the tab's most useful session that has run", () => {
    expect(pickSession(SESSIONS, "map", null)).toBe("Q");
    expect(pickSession(SESSIONS, "head-to-head", "R")).toBe("Q");
    expect(pickSession(RACE_RUN, "tyres", "Q")).toBe("R");
  });

  it("finds nothing when no fitting session has run", () => {
    expect(pickSession(SESSIONS, "tyres", null)).toBeNull();
    expect(pickSession([], "map", null)).toBeNull();
  });
});

describe("TelemetryView", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    nav.replace.mockClear();
    serve();
  });

  it("opens the speed map on the weekend's qualifying", async () => {
    renderView("round=19");
    expect(await screen.findByRole("radio", { name: "Qualifying", checked: true })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Speed Map", selected: true })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 2, name: /Kimi Antonelli · Q3/ })).toBeInTheDocument();
    expect(await screen.findByRole("combobox", { name: "Driver" })).toBeInTheDocument();
  });

  it("falls back to the schedule's default round when none is in the URL", async () => {
    renderView("");
    expect(await screen.findByRole("heading", { level: 2, name: /Kimi Antonelli · Q3/ })).toBeInTheDocument();
  });

  it("shows the head-to-head with its own pickers", async () => {
    renderView("tab=head-to-head&round=19&segment=2");
    expect(await screen.findByRole("combobox", { name: "Driver A" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Driver B" })).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Driver" })).not.toBeInTheDocument();
  });

  it("shows tyre degradation for a race that has run, offering race sessions only", async () => {
    serve({ available: true, pending: false, sessions: RACE_RUN });
    renderView("tab=tyres&round=19&session=Q");
    expect(await screen.findByRole("heading", { level: 2, name: /^Lap times rose/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Race", checked: true })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "Qualifying" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Driver" })).not.toBeInTheDocument();
  });

  it("says so when no race of the weekend has run yet", async () => {
    renderView("tab=tyres&round=19");
    expect(await screen.findByText("Not run yet")).toBeInTheDocument();
  });

  it("says so when the weekend has no race session at all", async () => {
    serve({ available: true, pending: false, sessions: [SESSIONS[0]] });
    renderView("tab=tyres&round=19");
    expect(await screen.findByText("No session of this kind on this weekend.")).toBeInTheDocument();
  });

  it("shows the backend's reason when the weekend's sessions are unavailable", async () => {
    serve({ available: false, pending: false, reason: "no_session", message: "OpenF1 has no such weekend." });
    renderView("round=19");
    expect(await screen.findByText("OpenF1 has no such weekend.")).toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: "Session" })).not.toBeInTheDocument();
  });

  it("waits for a round when the calendar is empty", async () => {
    server.use(http.get(apiUrl("/api/schedule/2026"), () => HttpResponse.json([])));
    renderView("", { year: 2026, schedule: [] });
    expect(await screen.findByText("Season calendar unavailable.")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Season" })).toBeEnabled();
    expect(screen.queryByRole("radiogroup", { name: "Session" })).not.toBeInTheDocument();
  });

  it("fetches another season's calendar rather than using the seed", async () => {
    renderView("year=2025&round=3");
    expect(await screen.findByRole("group", { name: "2025 race picker" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Next round" })).toBeEnabled();
    });
  });
});

describe("TelemetryView changes", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    nav.replace.mockClear();
    serve();
  });

  it("writes a new round to the URL and clears everything tied to the old one", async () => {
    const { user } = renderView("round=19&session=Q&a=ANT&b=RUS&lap=14&segment=2");
    await user.click(await screen.findByRole("button", { name: "Next round" }));
    expect(lastQuery().get("round")).toBe("20");
    for (const key of ["session", "a", "b", "lap", "segment"]) expect(lastQuery().has(key)).toBe(false);
  });

  it("writes a new season to the URL with no round", async () => {
    const { user } = renderView("round=19&session=Q&a=ANT");
    const season = screen.getByRole("combobox", { name: "Season" });
    expect(season).toHaveValue("2026");
    await user.selectOptions(season, "2025");
    expect(lastQuery().get("year")).toBe("2025");
    for (const key of ["round", "session", "a", "lap", "segment"]) expect(lastQuery().has(key)).toBe(false);
  });

  it("switches tab, keeping the rest", async () => {
    const { user } = renderView("round=19&session=Q");
    await user.click(await screen.findByRole("tab", { name: "Tyre Degradation" }));
    expect(lastQuery().get("tab")).toBe("tyres");
    expect(lastQuery().get("session")).toBe("Q");
  });

  it("switches session, dropping the lap and the qualifying part", async () => {
    const { user } = renderView("round=19&session=Q&lap=14&segment=2");
    await user.click(await screen.findByRole("radio", { name: "Practice 1" }));
    expect(lastQuery().get("session")).toBe("FP1");
    expect(lastQuery().has("lap")).toBe(false);
    expect(lastQuery().has("segment")).toBe(false);
  });

  it("writes the speed map's driver, lap and qualifying part", async () => {
    const { user } = renderView("round=19&session=Q&segment=3");
    await user.selectOptions(await screen.findByRole("combobox", { name: "Driver" }), "RUS");
    expect(lastQuery().get("a")).toBe("RUS");
    expect(lastQuery().has("lap")).toBe(false);
    await user.click(screen.getByRole("radio", { name: "Q2" }));
    expect(lastQuery().get("segment")).toBe("2");
    expect(lastQuery().has("lap")).toBe(false);
  });

  it("writes the head-to-head pair and qualifying part", async () => {
    const { user } = renderView("tab=head-to-head&round=19&session=Q&segment=3&lap=9");
    await user.selectOptions(await screen.findByRole("combobox", { name: "Driver B" }), "VER");
    expect(lastQuery().get("b")).toBe("VER");
    expect(lastQuery().has("lap")).toBe(false);
    await user.click(screen.getByRole("radio", { name: "Q1" }));
    expect(lastQuery().get("segment")).toBe("1");
  });
});
