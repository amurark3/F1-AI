import { act, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, POWER_UNITS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { CarView } from "./CarView";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

beforeEach(() => {
  vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
  server.use(
    http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
    http.get(apiUrl("/api/race-control/power-units/2026"), () => HttpResponse.json(POWER_UNITS_2026 as never)),
  );
});

describe("CarView", () => {
  it("lays out the crumb, the hero and the three sections", async () => {
    await act(() => {
      renderWithProviders(<CarView year={2026} segment="6" seed={Promise.resolve(POWER_UNITS_2026)} />);
      return Promise.resolve();
    });

    expect(screen.getByRole("link", { name: "← All cars" })).toHaveAttribute("href", "/race-control/power-units");
    expect(screen.getByRole("navigation", { name: "Other cars" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Car 6");
    expect(screen.getByRole("heading", { level: 2, name: "Elements" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Season" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Weekend by weekend" })).toBeInTheDocument();
    expect(screen.getByText(/^Source: FIA technical-delegate reports/)).toBeInTheDocument();
  });

  it("holds the h1 and a head and skeleton per section while the seed is still on its way", async () => {
    await act(() => {
      renderWithProviders(<CarView year={2026} segment="6" seed={new Promise(() => undefined)} />);
      return Promise.resolve();
    });

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Car 6");
    expect(screen.getByRole("heading", { level: 2, name: "Elements" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Season" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Weekend by weekend" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Other cars" })).not.toBeInTheDocument();
  });

  it("keeps the h1 and says why for an unknown car, with no empty heads", async () => {
    await act(() => {
      renderWithProviders(<CarView year={2026} segment="99" seed={Promise.resolve(POWER_UNITS_2026)} />);
      return Promise.resolve();
    });

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Car 99");
    expect(screen.getByText("No 2026 car runs as #99.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: "Elements" })).not.toBeInTheDocument();
  });
});
