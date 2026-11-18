import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { TeamSwitch } from "./TeamSwitch";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

beforeEach(() => {
  vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
});

describe("TeamSwitch", () => {
  it("links every team of the season in table order and marks the current one", () => {
    renderWithProviders(<TeamSwitch year={2026} teamId="ferrari" seed={DIRECTORY_2026} />);

    const nav = screen.getByRole("navigation", { name: "Teams" });
    const links = [...nav.querySelectorAll("a")];
    expect(links.map((link) => link.getAttribute("href"))).toEqual(
      DIRECTORY_2026.teams.map((team) => `/race-control/constructors/${team.id}`),
    );
    const current = screen.getByRole("link", { current: "page" });
    expect(current).toHaveTextContent("Ferrari");
    expect(current).toHaveAttribute("href", "/race-control/constructors/ferrari");
    expect(links.filter((link) => link.getAttribute("aria-current") === "page")).toHaveLength(1);
  });

  it("fetches the directory when unseeded, then shows the teams", async () => {
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026 as never)));
    renderWithProviders(<TeamSwitch year={2026} teamId="mercedes" seed={null} />);

    expect(document.querySelector("[aria-busy='true']")).toBeInTheDocument();
    expect(await screen.findByRole("link", { current: "page" })).toHaveTextContent("Mercedes");
  });

  it("says Teams unavailable with a Retry when the directory cannot be read", async () => {
    server.use(
      http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json({ detail: "x" }, { status: 500 })),
    );
    renderWithProviders(<TeamSwitch year={2026} teamId="mercedes" seed={null} />);

    expect(await screen.findByText("Teams unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
