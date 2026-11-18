import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useLiveTiming, type LivePosition, type SessionStatus } from "@/app/hooks/useLiveTiming";
import { NEUTRAL_TEAM_COLOR } from "@/app/lib/teamColors";
import { DIRECTORY_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { LiveTimingTower } from "./LiveTimingTower";

vi.mock("@/app/hooks/useLiveTiming", () => ({ useLiveTiming: vi.fn() }));

/** Hand-built rows, not a captured payload: a leader, a timed gap, a car with no team and a car with no gap. */
const POSITIONS: LivePosition[] = [
  {
    position: 1,
    driver: "VER",
    driver_number: 1,
    team: "Red Bull Racing",
    gap: "LEADER",
    last_lap: null,
    pit_stops: 0,
  },
  { position: 2, driver: "NOR", driver_number: 4, team: "McLaren", gap: "+2.481", last_lap: null, pit_stops: 0 },
  { position: 3, driver: "ALB", driver_number: 23, team: null, gap: "+9.002", last_lap: null, pit_stops: 1 },
  { position: 4, driver: "HAM", driver_number: 44, team: "Ferrari", gap: "—", last_lap: null, pit_stops: 0 },
];

const LIVE: SessionStatus = {
  status: "live",
  session_name: "Race",
  meeting_name: "São Paulo Grand Prix",
  starts_at: null,
  lap: 34,
  feed_age_seconds: 4.2,
};

const WEEKEND = { round: 20, status: "in_progress" };

function feed(overrides: Partial<ReturnType<typeof useLiveTiming>>) {
  vi.mocked(useLiveTiming).mockReturnValue({
    positions: POSITIONS,
    sessionStatus: LIVE,
    isConnected: true,
    ...overrides,
  });
}

function render(race: { round: number; status: string } | null | undefined = WEEKEND) {
  return renderWithProviders(<LiveTimingTower year={2026} race={race} />);
}

describe("LiveTimingTower", () => {
  beforeEach(() => {
    vi.mocked(useLiveTiming).mockClear();
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("opens no feed and renders nothing outside a race weekend", () => {
    feed({ sessionStatus: null });
    const { container } = render({ round: 20, status: "upcoming" });

    expect(useLiveTiming).toHaveBeenCalledWith(0, 0);
    expect(container).toBeEmptyDOMElement();
  });

  it("opens no feed when there is no race at all", () => {
    feed({ sessionStatus: null });
    const { container } = render(null);

    expect(useLiveTiming).toHaveBeenCalledWith(0, 0);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing while the session is on standby", () => {
    feed({ sessionStatus: { ...LIVE, status: "standby" } });
    const { container } = render();

    expect(useLiveTiming).toHaveBeenCalledWith(2026, 20);
    expect(container).toBeEmptyDOMElement();
  });

  it("names the session and lap, the feed's age and the connection above the running order", () => {
    feed({});
    render();

    expect(screen.getByRole("heading", { level: 2, name: "Race · Lap 34" })).toBeInTheDocument();
    expect(
      screen.getByText(/Gap to the leader, from OpenF1's position and interval feeds · updated 4 s ago/),
    ).toBeInTheDocument();
    expect(screen.getByText("Connected")).toHaveClass("text-rc-red-text");
    expect(screen.getByText("Live timing").firstElementChild).toHaveClass("bg-rc-red-text");
    expect(screen.getByText("Live timing").firstElementChild).not.toHaveClass("animate-pulse");
  });

  it("lists the order with the leader in gold, team edges, car numbers and gaps in mono", async () => {
    feed({});
    render();

    const rows = within(screen.getByRole("list", { name: "Running order" })).getAllByRole("listitem");
    expect(rows).toHaveLength(4);
    expect(rows[0].firstElementChild).toHaveClass("text-rc-gold");
    expect(rows[1].firstElementChild).toHaveClass("text-rc-ink-3");
    expect(within(rows[0]).getByText("Leader")).toHaveClass("text-rc-ink-3");
    expect(within(rows[1]).getByText("+2.481")).toHaveClass("font-mono", "font-semibold", "text-rc-ink");
    expect(within(rows[1]).getByText("4")).toHaveClass("hidden", "sm:block");
    // A car whose team the feed left out gets the neutral edge, never the first team's colour.
    expect(rows[2].children[1]).toHaveStyle({ backgroundColor: NEUTRAL_TEAM_COLOR });
    expect(rows[0].children[1]).not.toHaveStyle({ backgroundColor: NEUTRAL_TEAM_COLOR });
    expect(within(rows[3]).getByText("—")).toHaveClass("text-rc-ink-3");
    expect(screen.getByText("— = the feed has no gap for this car")).toBeInTheDocument();
    // The feed sends only the acronym; the names kit finds the surname in this season's directory.
    expect(await within(rows[0]).findByText("Verstappen")).toBeInTheDocument();
    expect(within(rows[0]).getByText("VER")).toBeInTheDocument();
  });

  it("prints the acronym once while the surname is not known yet", () => {
    feed({});
    render();

    expect(within(screen.getAllByRole("listitem")[0]).getAllByText("VER")).toHaveLength(1);
  });

  it("leaves out the no-gap note when every car has a gap", () => {
    feed({ positions: POSITIONS.slice(0, 2) });
    render();

    expect(screen.queryByText(/the feed has no gap/)).not.toBeInTheDocument();
  });

  it("titles a session with no lap count or feed age by its name alone", () => {
    feed({ sessionStatus: { ...LIVE, lap: null, feed_age_seconds: null } });
    render();

    expect(screen.getByRole("heading", { level: 2, name: "Race" })).toBeInTheDocument();
    expect(screen.queryByText(/updated/)).not.toBeInTheDocument();
  });

  it("falls back to a generic title when the session has no name", () => {
    feed({ sessionStatus: { ...LIVE, session_name: null, lap: null }, positions: [] });
    render();

    expect(screen.getByRole("heading", { level: 2, name: "Session" })).toBeInTheDocument();
    expect(screen.getByText("No session on track")).toBeInTheDocument();
  });

  it("says it is linking while the socket is not connected", () => {
    feed({ isConnected: false, positions: [] });
    render();

    expect(screen.getByText("Linking")).toBeInTheDocument();
    expect(screen.getByText("Connecting to live timing…")).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("waits for the session's timing data once connected with no rows", () => {
    feed({ positions: [] });
    render();

    expect(screen.getByText("Waiting for Race timing data…")).toBeInTheDocument();
  });
});
