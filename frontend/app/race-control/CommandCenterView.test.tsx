import { act, screen } from "@testing-library/react";
import { delay, http, HttpResponse, type JsonBodyType } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useLiveTiming } from "@/app/hooks/useLiveTiming";
import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, OVERVIEW_SEGMENTS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { CommandCenterView, type OverviewSeeds } from "./CommandCenterView";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));
vi.mock("@/app/hooks/useLiveTiming", () => ({ useLiveTiming: vi.fn() }));

const SEGMENTS = ["shell", "strategy", "predictions", "weather", "circuit"] as const;

type Bodies = Partial<Record<(typeof SEGMENTS)[number], JsonBodyType>>;

/**
 * The server's seeds from the captured segments, any of them replaced. The cast stands in for a
 * fixture whose race lacks the fields the view never reads (`is_sprint`).
 */
function seedOf(bodies: Bodies = {}): OverviewSeeds {
  const resolved = { ...OVERVIEW_SEGMENTS_2026, ...bodies };
  return Object.fromEntries(
    SEGMENTS.map((name) => [name, Promise.resolve(resolved[name])]),
  ) as unknown as OverviewSeeds;
}

/** Renders the view inside `act`, so the seed promises settle and the slots fill. */
async function renderView(seeds: OverviewSeeds) {
  let rendered: ReturnType<typeof renderWithProviders> | undefined;
  await act(() => {
    rendered = renderWithProviders(<CommandCenterView year={2026} seeds={seeds} />);
    return Promise.resolve();
  });
  return rendered!;
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

const FAILED_SEED = seedOf({ shell: null, strategy: null, predictions: null, weather: null, circuit: null });

/** A seed the server never delivers. */
const NEVER = (): void => undefined;

describe("CommandCenterView", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    vi.mocked(useLiveTiming).mockReturnValue({ positions: [], sessionStatus: null, isConnected: false });
    serve();
  });

  it("lays the weekend out under one h1: hero, four tiles, then every panel on its own heading", async () => {
    await renderView(seedOf());

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

  it("reads each panel's empty branches when the segments carry nothing", async () => {
    const bodies: Bodies = {
      shell: { ...OVERVIEW_SEGMENTS_2026.shell, season: undefined },
      strategy: {},
      predictions: {},
      weather: {},
      circuit: {},
    };
    serve(bodies);
    await renderView(seedOf(bodies));

    expect(screen.getByText(/^Command Center · Round \d+ ·/)).not.toHaveTextContent("/");
    expect(screen.getByText("The baseline plan has not arrived yet.")).toBeInTheDocument();
    expect(screen.getByText("The podium appears once the race model has inputs for this weekend.")).toBeInTheDocument();
    expect(screen.getByText("No risks graded for this weekend.")).toBeInTheDocument();
    expect(screen.getByText("Forecast feed offline")).toBeInTheDocument();
  });

  it("shows the plain hero while the shell has no race", async () => {
    serve({ shell: {} });
    await renderView(seedOf({ shell: {} }));

    expect(screen.getByRole("heading", { level: 1, name: "Command Center" })).toBeInTheDocument();
    expect(screen.getByText("The next race weekend appears here once the calendar is published.")).toBeInTheDocument();
  });

  it("gives the reason when the shell failed and there is no race to show", async () => {
    serve({ shell: { error: "Calendar offline" } });
    await renderView(FAILED_SEED);

    expect((await screen.findAllByText("Calendar offline")).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { level: 1, name: "Command Center" })).toBeInTheDocument();
  });

  it("holds the hero as a skeleton while the shell loads", async () => {
    server.use(
      http.get(apiUrl("/api/race-control/overview/2026/shell"), async () => {
        await delay("infinite");
        return HttpResponse.json({});
      }),
    );
    const { container } = await renderView(FAILED_SEED);

    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    expect(container.querySelector(".h-\\[460px\\]")).toBeInTheDocument();
  });

  it("fills each slot from its own segment: a circuit that never arrives holds only its slot", async () => {
    const { container } = await renderView({ ...seedOf(), circuit: new Promise(NEVER) });
    NEVER();

    expect(await screen.findByRole("heading", { level: 2, name: "Projected podium" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: "History" })).not.toBeInTheDocument();
    expect(container.querySelector(".h-\\[420px\\]")).toBeInTheDocument();
  });
});
