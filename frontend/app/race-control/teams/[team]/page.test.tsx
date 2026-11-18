import { beforeEach, describe, expect, it, vi } from "vitest";

import TeamDetailRedirect from "./page";

const nav = vi.hoisted(() => ({ redirect: vi.fn() }));

vi.mock("next/navigation", () => ({ redirect: nav.redirect }));

describe("the old team detail URL", () => {
  beforeEach(() => nav.redirect.mockClear());

  it("redirects a slug to the team's page", async () => {
    await TeamDetailRedirect({ params: Promise.resolve({ team: "mercedes" }) });

    expect(nav.redirect).toHaveBeenCalledWith("/race-control/constructors/mercedes");
  });
});
