import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026 } from "@/test/fixtures";
import { DEBRIEF_R19 } from "@/test/fixtures/debrief";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { PenaltyTimeline } from "./PenaltyTimeline";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const PENALTIES = DEBRIEF_R19.penalties;

describe("PenaltyTimeline", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("lists the four in-race and three post-race penalties of Mexico City", () => {
    renderWithProviders(<PenaltyTimeline penalties={PENALTIES} />);

    expect(screen.getByRole("heading", { name: "7 drivers penalised" })).toBeInTheDocument();
    expect(
      screen.getByText("In-race from race control · post-race from the FIA final classification (doc 86)"),
    ).toBeInTheDocument();
    const rows = within(screen.getByRole("list", { name: "Penalties" })).getAllByRole("listitem");
    expect(rows).toHaveLength(7);
    expect(rows[0]).toHaveTextContent("L12");
    expect(rows[0]).toHaveTextContent("5 s");
    expect(rows[0]).toHaveTextContent("Leaving the track and gaining an advantage · served");
    expect(rows[4]).toHaveTextContent("Post-race");
    expect(rows[4]).toHaveTextContent("Causing a collision · FIA doc 79 · P7 → P13");
  });

  it("names the penalty when it is not a time penalty, and leaves out missing parts", () => {
    renderWithProviders(
      <PenaltyTimeline
        penalties={{
          available: true,
          fia_document: null,
          in_race: [
            {
              lap: null,
              car: 3,
              driver_code: "VER",
              driver_name: "Max Verstappen",
              penalty: "Drive through penalty",
              seconds: null,
              offence: null,
              served: false,
            },
          ],
          post_race: [
            {
              driver_code: "HAM",
              driver_name: "Lewis Hamilton",
              car: null,
              ruling: "Drive through penalty",
              seconds: null,
              reason: null,
              document: null,
              road_position: null,
              position: null,
            },
          ],
        }}
      />,
    );

    const rows = screen.getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("In race");
    expect(rows[0]).toHaveTextContent("Drive through penalty");
    expect(rows[1]).toHaveTextContent("Post-race");
    expect(rows[1]).not.toHaveTextContent("FIA doc");
  });

  it("says there were no penalties", () => {
    renderWithProviders(<PenaltyTimeline penalties={{ ...PENALTIES, in_race: [], post_race: [] }} />);

    expect(screen.getByRole("heading", { name: "No penalties" })).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("says when OpenF1 has no record of the race", () => {
    renderWithProviders(<PenaltyTimeline penalties={{ ...PENALTIES, available: false, in_race: [], post_race: [] }} />);

    expect(screen.getByText("OpenF1 has no race control record for this race.")).toBeInTheDocument();
  });
});
