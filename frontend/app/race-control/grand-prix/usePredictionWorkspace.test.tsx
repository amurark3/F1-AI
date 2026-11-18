import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useHubUrlState } from "./useHubUrlState";

const nav = vi.hoisted(() => ({ search: "round=19", replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(nav.search),
  useRouter: () => ({ replace: nav.replace }),
  usePathname: () => "/race-control/grand-prix",
}));

describe("useHubUrlState", () => {
  it("replaces the URL with the bare path when nothing is selected any more", () => {
    nav.search = "round=19";
    const { result } = renderHook(() => useHubUrlState());

    act(() => result.current.update({ round: null }));

    expect(nav.replace).toHaveBeenCalledWith("/race-control/grand-prix", { scroll: false });
  });
});
