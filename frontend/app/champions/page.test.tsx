import { describe, expect, it, vi } from "vitest";

import ChampionsRedirectPage from "./page";

const navigation = vi.hoisted(() => ({ redirect: vi.fn() }));
vi.mock("next/navigation", () => navigation);

describe("/champions", () => {
  it("redirects to the Race Control champions page", () => {
    ChampionsRedirectPage();

    expect(navigation.redirect).toHaveBeenCalledWith("/race-control/champions");
  });
});
