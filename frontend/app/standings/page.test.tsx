import { describe, expect, it, vi } from "vitest";

import StandingsRedirectPage from "./page";

const nav = vi.hoisted(() => ({ redirect: vi.fn() }));

vi.mock("next/navigation", () => ({ redirect: nav.redirect }));

describe("the /standings redirect", () => {
  it("sends the old URL to the Standings page", () => {
    StandingsRedirectPage();

    expect(nav.redirect).toHaveBeenCalledWith("/race-control/teams");
  });
});
