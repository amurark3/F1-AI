import { screen } from "@testing-library/react";
import { delay, http, HttpResponse, type JsonBodyType } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useLiveTiming } from "@/app/hooks/useLiveTiming";
import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, OVERVIEW_SEGMENTS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { CommandCenterView, type OverviewSeed } from "./CommandCenterView";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));
vi.mock("@/app/hooks/useLiveTiming", () => ({ useLiveTiming: vi.fn() }));

const SEGMENTS = ["shell", "strategy", "predictions", "weather", "circuit"] as const;

type Bodies = Partial<Record<(typeof SEGMENTS)[number], JsonBodyType>>;

/**
 * The server's seed from the captured segments, any of them replaced. The cast stands in for a
 * fixture whose race lacks the fields the view never reads (`is_sprint`).
 */
function seedOf(bodies: Bodies = {}): OverviewSeed {
  return { year: 2026, ...OVERVIEW_SEGMENTS_2026, ...bodies } as unknown as OverviewSeed;
}

/** Serves the five segments, each overridable by a body. */
function serve(bodies: Bodies = {}) {
  server.use(
    http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
    ...SEGMENTS.map((segment) =>
      http.get(apiUrl(`/api/race-control/overview/2026/${segment}`), () =>
        HttpResponse.json(segment in bodies ? bodies[segment] : OVERVIEW_SEGMENTS_2026[segment]),
      ),
    ),
  );
}

const FAILED_SEED: OverviewSeed = {
  year: 2026,
  shell: null,
  strategy: null,
  predictions: null,
  weather: null,
  circuit: null,
};

describe("CommandCenterView", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    vi.mocked(useLiveTiming).mockReturnValue({ positions: [], sessionStatus: null, isConnected: false });
    serve();
  });

  it("lays the weekend out under one h1: hero, four tiles, then every panel on its own heading", () => {
    renderWithProviders(<CommandCenterView seed={seedOf()} />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(OVERVIEW_SEGMENTS_2026.shell.race?.name ?? "");
    expect(screen.getByText(/^Command Center · Round/)).toBeInTheDocument();
    for (const name of ["Race-day rain", "Pit lane time", "Title gap", "Pole → win here"]) {
      expect(screen.getByRole("group", { name })).toBeInTheDocument();
    }
    for (const name of [
      "Weather, session by session",
      "What's at stake",
      "Projected podium",
      "History",
      "Weekend risks",
    ]) {
      expect(screen.getByRole("heading", { level: 2, name })).toBeInTheDocument();
    }
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: OVERVIEW_SEGMENTS_2026.strategy.strategy_context?.primary_call.title,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Sources & assumptions")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Running order" })).not.toBeInTheDocument();
    expect(useLiveTiming).toHaveBeenCalledWith(0, 0);
  });

  it("reads each panel's empty branches when the segments carry nothing", () => {
    const bodies: Bodies = {
      shell: { ...OVERVIEW_SEGMENTS_2026.shell, season: undefined },
      strategy: {},
      predictions: {},
      weather: {},
      circuit: {},
    };
    serve(bodies);
    renderWithProviders(<CommandCenterView seed={seedOf(bodies)} />);

    expect(screen.getByText(/^Command Center · Round \d+ ·/)).not.toHaveTextContent("/");
    expect(screen.getByText("The baseline plan has not arrived yet.")).toBeInTheDocument();
    expect(screen.getByText("The podium appears once the race model has inputs for this weekend.")).toBeInTheDocument();
    expect(screen.getByText("No risks graded for this weekend.")).toBeInTheDocument();
    expect(screen.getByText("Forecast feed offline")).toBeInTheDocument();
  });

  it("shows the plain hero while the shell has no race", () => {
    serve({ shell: {} });
    renderWithProviders(<CommandCenterView seed={seedOf({ shell: {} })} />);

    expect(screen.getByRole("heading", { level: 1, name: "Command Center" })).toBeInTheDocument();
    expect(screen.getByText("The next race weekend appears here once the calendar is published.")).toBeInTheDocument();
  });

  it("gives the reason when the shell failed and there is no race to show", async () => {
    serve({ shell: { error: "Calendar offline" } });
    renderWithProviders(<CommandCenterView seed={FAILED_SEED} />);

    expect((await screen.findAllByText("Calendar offline")).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { level: 1, name: "Command Center" })).toBeInTheDocument();
  });

  it("holds the hero as a skeleton while the shell loads", () => {
    server.use(
      http.get(apiUrl("/api/race-control/overview/2026/shell"), async () => {
        await delay("infinite");
        return HttpResponse.json({});
      }),
    );
    const { container } = renderWithProviders(<CommandCenterView seed={FAILED_SEED} />);

    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    expect(container.querySelector(".h-\\[460px\\]")).toBeInTheDocument();
  });
});
