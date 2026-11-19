import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026 } from "@/test/fixtures";
import { DEBRIEF_R19 } from "@/test/fixtures/debrief";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { sparePhrase, TitleBanners } from "./TitleBanner";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const [TITLE] = DEBRIEF_R19.summary.titles;

describe("TitleBanners", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("announces the drivers' champion with the margin that decided it", () => {
    renderWithProviders(<TitleBanners titles={[TITLE]} year={2026} />);

    expect(screen.getByText("Champion")).toBeInTheDocument();
    expect(
      screen.getByText(/2026 World Champion with 4 races to spare · 380 points, 119 clear of Max Verstappen/),
    ).toBeInTheDocument();
    expect(screen.getByText("Kimi Antonelli")).toBeInTheDocument();
    expect(screen.queryByText("Provisional")).not.toBeInTheDocument();
  });

  it("announces the constructors' champions, provisional, at the final round", () => {
    const constructors = {
      ...TITLE,
      table: "constructors" as const,
      name: "Mercedes",
      races_left: 0,
      provisional: true,
      lead: null,
      runner_up: null,
    };
    renderWithProviders(<TitleBanners titles={[constructors]} year={2026} />);

    expect(screen.getByText("Constructors' champion")).toBeInTheDocument();
    expect(screen.getByText(/2026 World Champions at the final round · 380 points$/)).toBeInTheDocument();
    expect(screen.getByText("Provisional")).toBeInTheDocument();
  });

  it("draws nothing when no title was decided", () => {
    const { container } = renderWithProviders(<TitleBanners titles={[]} year={2026} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("says races to spare in the singular, and nothing when the data does not say", () => {
    expect(sparePhrase(1)).toBe(" with 1 race to spare");
    expect(sparePhrase(4)).toBe(" with 4 races to spare");
    expect(sparePhrase(0)).toBe(" at the final round");
    expect(sparePhrase(null)).toBe("");
  });
});
