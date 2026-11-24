import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const store = vi.hoisted(() => ({
  startServerProbe: vi.fn(),
  getServerStatus: vi.fn(),
  getServerStatusOnServer: vi.fn(() => ({ status: "unknown" })),
  subscribeServerStatus: vi.fn((onChange: () => void) => {
    store.listeners.push(onChange);
    return () => undefined;
  }),
  listeners: [] as Array<() => void>,
}));
vi.mock("../lib/serverStatus", () => store);

import { useServerStatus } from "./useServerStatus";

const READY = { status: "ready" };
const WARMING = { status: "warming" };

describe("useServerStatus", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    store.getServerStatus.mockReturnValue(READY);
  });

  it("starts the shared probe and reads the shared state", () => {
    const { result } = renderHook(() => useServerStatus());

    expect(store.startServerProbe).toHaveBeenCalledTimes(1);
    expect(result.current).toBe(READY);

    store.getServerStatus.mockReturnValue(WARMING);
    act(() => store.listeners.forEach((listener) => listener()));
    expect(result.current).toBe(WARMING);
  });
});
