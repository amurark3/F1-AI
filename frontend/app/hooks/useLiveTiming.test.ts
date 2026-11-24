import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useLiveTiming, type LivePosition, type SessionStatus } from "./useLiveTiming";

class MockSocket {
  static instances: MockSocket[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  close = vi.fn();

  constructor(readonly url: string) {
    MockSocket.instances.push(this);
  }

  send(payload: unknown) {
    this.onmessage?.({ data: typeof payload === "string" ? payload : JSON.stringify(payload) } as MessageEvent);
  }
}

const row: LivePosition = {
  position: 1,
  driver: "Max Verstappen",
  driver_number: 1,
  team: "Red Bull",
  gap: "Leader",
  last_lap: "1:30.000",
  pit_stops: 1,
};
const status = (state: SessionStatus["status"]): SessionStatus => ({
  status: state,
  session_name: "Race",
  meeting_name: "Test GP",
  starts_at: null,
  lap: 3,
  feed_age_seconds: 1,
});

const socket = () => MockSocket.instances[0];

describe("useLiveTiming", () => {
  beforeEach(() => {
    MockSocket.instances = [];
    vi.stubGlobal("WebSocket", MockSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("opens no socket without a live weekend", () => {
    const { result } = renderHook(() => useLiveTiming(0, 0));

    expect(MockSocket.instances).toHaveLength(0);
    expect(result.current).toEqual({ positions: [], sessionStatus: null, isConnected: false });
  });

  it("connects to the weekend's feed over ws and follows its connection state", () => {
    const { result } = renderHook(() => useLiveTiming(2026, 5));

    expect(socket().url).toBe("ws://localhost:8000/api/live/2026/5");
    act(() => socket().onopen?.());
    expect(result.current.isConnected).toBe(true);
    act(() => socket().onerror?.());
    expect(result.current.isConnected).toBe(false);
    act(() => socket().onopen?.());
    act(() => socket().onclose?.());
    expect(result.current.isConnected).toBe(false);
  });

  it("keeps rows while the session is live and clears them once it is not", () => {
    const { result } = renderHook(() => useLiveTiming(2026, 5));

    act(() => socket().send({ type: "positions", data: [row] }));
    act(() => socket().send({ type: "session_status", data: status("live") }));
    expect(result.current.positions).toEqual([row]);
    expect(result.current.sessionStatus?.status).toBe("live");

    act(() => socket().send({ type: "session_status", data: status("finished") }));
    expect(result.current.positions).toEqual([]);
    expect(result.current.sessionStatus?.status).toBe("finished");
  });

  it("ignores heartbeats, unknown types and malformed frames", () => {
    const { result } = renderHook(() => useLiveTiming(2026, 5));

    act(() => socket().send({ type: "positions", data: [row] }));
    act(() => socket().send({ type: "ping" }));
    act(() => socket().send({ type: "mystery" }));
    act(() => socket().send("not json"));

    expect(result.current.positions).toEqual([row]);
  });

  it("closes the socket and empties the tower on unmount", () => {
    const { unmount } = renderHook(() => useLiveTiming(2026, 5));

    unmount();

    expect(socket().close).toHaveBeenCalledOnce();
  });

  describe("after the connection drops", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    const latest = () => MockSocket.instances.at(-1);

    it("reconnects, backing off from 1 s and doubling up to 30 s", () => {
      renderHook(() => useLiveTiming(2026, 5));
      const delays = [1_000, 2_000, 4_000, 8_000, 16_000, 30_000, 30_000];

      delays.forEach((delay, i) => {
        act(() => latest()?.onclose?.());
        act(() => {
          vi.advanceTimersByTime(delay - 1);
        });
        expect(MockSocket.instances).toHaveLength(i + 1);
        act(() => {
          vi.advanceTimersByTime(1);
        });
        expect(MockSocket.instances).toHaveLength(i + 2);
      });
      expect(latest()?.url).toBe("ws://localhost:8000/api/live/2026/5");
    });

    it("starts the back-off over once a reconnect opens", () => {
      const { result } = renderHook(() => useLiveTiming(2026, 5));

      act(() => latest()?.onclose?.());
      act(() => {
        vi.advanceTimersByTime(1_000);
      });
      act(() => latest()?.onclose?.());
      act(() => {
        vi.advanceTimersByTime(2_000);
      });
      act(() => latest()?.onopen?.());
      expect(result.current.isConnected).toBe(true);

      act(() => latest()?.onclose?.());
      act(() => {
        vi.advanceTimersByTime(1_000);
      });
      expect(MockSocket.instances).toHaveLength(4);
    });

    it("stops reconnecting on unmount, and a late close from the old socket is ignored", () => {
      const { unmount } = renderHook(() => useLiveTiming(2026, 5));

      act(() => latest()?.onclose?.());
      unmount();
      act(() => {
        vi.advanceTimersByTime(60_000);
      });
      expect(MockSocket.instances).toHaveLength(1);

      act(() => socket().onclose?.());
      act(() => {
        vi.advanceTimersByTime(60_000);
      });
      expect(MockSocket.instances).toHaveLength(1);
    });
  });
});
