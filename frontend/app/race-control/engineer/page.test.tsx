import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { OVERVIEW_SEGMENTS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import Page, { metadata } from "./page";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

describe("the AI Engineer page", () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(
      http.get(apiUrl("/api/race-control/overview/:year/shell"), () => HttpResponse.json(OVERVIEW_SEGMENTS_2026.shell)),
    );
  });

  it("is titled for the engineer", () => {
    expect(metadata.title).toBe("AI Race Engineer | F1 AI");
    expect(metadata.description).toContain("Formula 1");
  });

  it("renders the engineer", async () => {
    renderWithProviders(<Page />);

    expect(screen.getByRole("heading", { level: 1, name: "AI Engineer" })).toBeInTheDocument();
    expect(await screen.findByRole("textbox", { name: "Ask the AI Engineer" })).toBeInTheDocument();
  });
});
