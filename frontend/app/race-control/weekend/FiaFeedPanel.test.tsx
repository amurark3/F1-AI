import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, WEEKEND_FEED_2026_R19 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { FiaFeedPanel } from "./FiaFeedPanel";

import type { FeedEvent, WeekendFeed } from "./fiaFeedModel";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const FEED_URL = apiUrl("/api/weekend/:year/:round/feed");
const COMPLETED = { round: 19, status: "completed" };

let feedCalls = 0;

function serve(body: unknown): void {
  server.use(
    http.get(FEED_URL, () => {
      feedCalls += 1;
      return HttpResponse.json(body as Record<string, unknown>);
    }),
  );
}

function rowOf(label: string): HTMLElement {
  return screen.getByRole("link", { name: new RegExp(`^${label} `) }).closest("li")!;
}

/** Hand-built events for the states the Mexico weekend never had; not captured from the backend. */
function made(number: number | null, partial: Record<string, unknown>): FeedEvent {
  return {
    number,
    title: `Doc ${number} - Hand built`,
    kind: "penalty",
    published: "",
    published_at: "2026-11-01T12:00:00+00:00",
    url: `https://example.test/${number ?? "none"}-${String(partial.kind)}.pdf`,
    withdrawn: null,
    data: null,
    unread: null,
    ...partial,
  };
}

const DECISION = {
  document: 1,
  status: "decided",
  car: 7,
  driver: null,
  competitor: null,
  session: "Race",
  incident_time: null,
  offence: "Unsafe release",
  articles: [],
  decision: "Fine as printed.",
  outcomes: [],
  hearing: null,
};

function handBuilt(events: FeedEvent[], latest: number | null = 9): WeekendFeed {
  return { year: 2026, round: 19, event: "Test Grand Prix", latest, events };
}

describe("FiaFeedPanel", () => {
  beforeEach(() => {
    feedCalls = 0;
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("lists the Mexico weekend's decisions, newest first, previewing the newest eight", async () => {
    serve(WEEKEND_FEED_2026_R19);
    renderWithProviders(<FiaFeedPanel year={2026} race={COMPLETED} />);

    expect(await screen.findByRole("heading", { name: "24 decisions, 98 laps deleted" })).toBeInTheDocument();
    expect(screen.getByText(/Mexico City Grand Prix · Newest first/)).toBeInTheDocument();
    expect(screen.queryByText("Weekend live")).not.toBeInTheDocument();
    const list = screen.getByRole("list", { name: "FIA documents, newest first" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(8);

    const doc79 = screen.getByRole("link", { name: /^Doc 79 / });
    expect(doc79).toHaveAttribute("href", WEEKEND_FEED_2026_R19.events.find((e) => e.number === 79)!.url);
    expect(doc79).toHaveAttribute("target", "_blank");
    expect(doc79).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(rowOf("Doc 79")).getByText("Oscar Piastri")).toBeInTheDocument();
    expect(within(rowOf("Doc 79")).getByText("10 s time penalty")).toBeInTheDocument();
    expect(rowOf("Doc 85")).toHaveClass("border-l-f1-red");
    expect(rowOf("Doc 83")).not.toHaveClass("border-l-f1-red");
    expect(within(rowOf("Doc 82")).getByText("Summoned")).toBeInTheDocument();
    expect(within(rowOf("Doc 82")).getByText(/hearing 19:00 circuit time/)).toBeInTheDocument();
    expect(screen.getByText(/^44 of 58 documents/)).toHaveTextContent("latest Doc 86");
  });

  it("opens the whole list, with deleted laps and both grids", async () => {
    const user = userEvent.setup();
    serve(WEEKEND_FEED_2026_R19);
    renderWithProviders(<FiaFeedPanel year={2026} race={COMPLETED} />);

    const button = await screen.findByRole("button", { name: "Show all 44" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    await user.click(button);

    const list = screen.getByRole("list", { name: "FIA documents, newest first" });
    expect(within(list).getAllByRole("listitem").length).toBeGreaterThanOrEqual(44);
    expect(screen.getByRole("button", { name: "Show the newest 8" })).toHaveAttribute("aria-expanded", "true");
    const sheet = rowOf("Doc 80");
    expect(within(sheet).getByText("13 lap times deleted")).toBeInTheDocument();
    expect(within(sheet).getByText("Track limits · 8 cars")).toBeInTheDocument();
    expect(within(sheet).getByText("#81", { exact: false, selector: "span[title]" })).toHaveAttribute(
      "title",
      "Oscar Piastri McLaren Mastercard F1 Team",
    );
    expect(within(rowOf("Doc 67")).getByText("Final starting grid")).toBeInTheDocument();
    expect(within(rowOf("Doc 67")).getByText("Final")).toBeInTheDocument();
    expect(within(rowOf("Doc 60")).getByText("Provisional starting grid")).toBeInTheDocument();
    expect(within(rowOf("Doc 60")).getByText("Provisional")).toBeInTheDocument();
    expect(screen.getAllByText(/50 place grid penalty/).length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Show the newest 8" }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(8);
  });

  it("tags a live weekend and polls it", async () => {
    serve(WEEKEND_FEED_2026_R19);
    renderWithProviders(<FiaFeedPanel year={2026} race={{ round: 19, status: "in_progress" }} />);

    expect(await screen.findByText("Weekend live")).toBeInTheDocument();
  });

  it.each([
    ["an upcoming round", 2026, { round: 19, status: "upcoming" }],
    ["no race", 2026, null],
    ["a season before 2019", 2018, COMPLETED],
  ])("renders nothing and asks nothing for %s", (_name, year, race) => {
    serve(WEEKEND_FEED_2026_R19);
    const { container } = renderWithProviders(<FiaFeedPanel year={year} race={race} />);

    expect(container).toBeEmptyDOMElement();
    expect(feedCalls).toBe(0);
  });

  it("labels the states the Mexico weekend never had", async () => {
    const sheet = {
      document: 3,
      session: "Qualifying",
      date: "2026-11-01",
      reason: "yellow_flags",
      fact: "",
      laps: [{ car: 4, turn: null, entrant: "Lando Norris McLaren", time_of_day: "10:00:00", lap_time: null }],
    };
    serve(
      handBuilt(
        [
          made(9, { data: { ...DECISION, car: 9, driver: "Hand Driver" }, withdrawn: "withdrawn by Doc 12" }),
          made(8, { title: "Doc 8 - Corrected Decision", data: { ...DECISION, car: 8, driver: "Kim Corrected" } }),
          made(7, { title: "Doc 7 - Infringement - Car 7", unread: "pdftotext exploded at /tmp/x" }),
          made(6, {
            data: { ...DECISION, status: "summoned", car: 6, competitor: "Team Only", hearing: null, decision: null },
          }),
          made(5, { data: { ...DECISION, car: 5, driver: "Plain Penalty" } }),
          made(4, {
            kind: "grid",
            data: { document: 4, final: false, slots: [], pit_lane: [], notes: [], penalties: [] },
          }),
          made(3, { kind: "deleted_laps", data: sheet }),
          made(2, { kind: "deleted_laps", data: sheet, withdrawn: "withdrawn by Doc 12" }),
          made(null, { published_at: null, data: { ...DECISION, car: 2, driver: "No Number" } }),
          made(1, {
            data: {
              ...DECISION,
              car: 1,
              driver: null,
              competitor: null,
              outcomes: [{ kind: "no_further_action", value: null }],
            },
          }),
        ],
        null,
      ),
    );
    renderWithProviders(<FiaFeedPanel year={2026} race={COMPLETED} />);
    await screen.findByRole("list", { name: "FIA documents, newest first" });
    await userEvent.setup().click(screen.getByRole("button", { name: "Show all 10" }));

    const withdrawn = rowOf("Doc 9");
    expect(within(withdrawn).getByText("Hand Driver").closest(".line-through")).not.toBeNull();
    expect(within(withdrawn).getByText("Withdrawn: withdrawn by Doc 12")).toBeInTheDocument();
    expect(within(withdrawn).getByText("Withdrawn")).toBeInTheDocument();
    expect(withdrawn).not.toHaveClass("border-l-f1-red");
    expect(within(rowOf("Doc 8")).getByText("Corrected")).toBeInTheDocument();
    expect(within(rowOf("Doc 7")).getByText(/Couldn.t read this PDF yet/)).toBeInTheDocument();
    expect(screen.queryByText(/pdftotext/)).not.toBeInTheDocument();
    expect(within(rowOf("Doc 6")).getByText("Team Only")).toBeInTheDocument();
    expect(within(rowOf("Doc 5")).getByText("Fine as printed.")).toBeInTheDocument();
    expect(within(rowOf("Doc 4")).getByText("No grid penalties")).toBeInTheDocument();
    expect(within(rowOf("Doc 3")).getAllByText("1 lap time deleted")[0]).toBeInTheDocument();
    expect(within(rowOf("Doc 3")).getAllByText("Double yellow flags · 1 car")[0]).toBeInTheDocument();
    expect(within(rowOf("FIA document")).getByText("No Number")).toBeInTheDocument();
    expect(within(rowOf("FIA document")).getAllByText("—").length).toBeGreaterThanOrEqual(2);
    expect(within(rowOf("Doc 1")).getByText("Car 1")).toBeInTheDocument();
    expect(screen.getByText(/^10 of 10 documents/).textContent).not.toContain("latest Doc");
  });

  it("says so before the FIA has published anything", async () => {
    serve({ year: 2026, round: 19, event: null, latest: null, events: [] });
    renderWithProviders(<FiaFeedPanel year={2026} race={COMPLETED} />);

    expect(await screen.findByRole("heading", { name: "No documents yet" })).toBeInTheDocument();
    expect(screen.getByText(/hasn't published a document for this weekend yet/)).toBeInTheDocument();
  });

  it("counts the other documents when none is a decision", async () => {
    const other = (number: number) => made(number, { kind: "pirelli" });
    serve(handBuilt([other(3), other(2), other(1)]));
    const { unmount } = renderWithProviders(<FiaFeedPanel year={2026} race={COMPLETED} />);
    expect(await screen.findByRole("heading", { name: "No decisions yet" })).toBeInTheDocument();
    expect(screen.getByText(/3 other documents are out\./)).toBeInTheDocument();
    unmount();

    serve(handBuilt([other(1)]));
    renderWithProviders(<FiaFeedPanel year={2026} race={COMPLETED} />);
    expect(await screen.findByText(/1 other document is out\./)).toBeInTheDocument();
  });

  it("offers a retry when the feed cannot be read", async () => {
    serve({ year: 2026, round: 19, event: null, latest: null, events: [], error: "Try again shortly.", error_id: "x" });
    renderWithProviders(<FiaFeedPanel year={2026} race={COMPLETED} />);

    expect((await screen.findAllByText(/FIA decisions unavailable/)).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /Retry/ })).toBeInTheDocument();
  });
});
