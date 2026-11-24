import { describe, expect, it, vi } from "vitest";

import { fetchFromBackend } from "./backend";
import { getDirectory, getDriverProfile, getTeamProfile, getTeamsIndex } from "./profiles";
import { REVALIDATE } from "./revalidate";

vi.mock("./backend", () => ({ fetchFromBackend: vi.fn().mockResolvedValue(null) }));

describe("profile reads", () => {
  it("asks for each profile document with its own clock and tags", async () => {
    await getDirectory(2026);
    await getTeamsIndex(2026);
    await getTeamProfile(2026, "red-bull");
    await getDriverProfile(2026, "max-verstappen");

    expect(vi.mocked(fetchFromBackend).mock.calls).toEqual([
      ["/api/profiles/2026/directory", { revalidate: REVALIDATE.ENTRY_LIST, tags: ["profiles", "profiles:2026"] }],
      ["/api/profiles/2026/teams", { revalidate: REVALIDATE.STANDINGS, tags: ["profiles", "profiles:2026"] }],
      [
        "/api/profiles/2026/teams/red-bull",
        { revalidate: REVALIDATE.STANDINGS, tags: ["profiles", "profiles:2026", "profiles:team:red-bull"] },
      ],
      [
        "/api/profiles/2026/drivers/max-verstappen",
        { revalidate: REVALIDATE.STANDINGS, tags: ["profiles", "profiles:2026", "profiles:driver:max-verstappen"] },
      ],
    ]);
  });

  it("escapes an id before it joins the path", async () => {
    await getTeamProfile(2026, "a/b");

    expect(vi.mocked(fetchFromBackend)).toHaveBeenLastCalledWith("/api/profiles/2026/teams/a%2Fb", expect.anything());
  });
});
