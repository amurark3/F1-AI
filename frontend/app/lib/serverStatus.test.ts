import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { API_BASE } from "@/app/constants/api";
import { READY, WARMING } from "@/test/fixtures";

import type * as ServerStatusStore from "./serverStatus";

type ServerStatusModule = typeof ServerStatusStore;
type ServerStatus = ServerStatusStore.ServerStatus;
type FetchMock = ReturnType<typeof vi.fn<typeof fetch>>;

const READY_URL = `${API_BASE}/api/ready`;
const PROBE_TIMEOUT_MS = 4_000;
const PROBE_INTERVAL_MS = 3_000;
const GIVE_UP_MS = 120_000;
const RECHECK_COOLDOWN_MS = 10_000;

/** A 200 carrying `body` as JSON, as the backend answers `/api/ready`. */
function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

/** Answers every probe with `body`; each call gets its own response, since a body reads once. */
function alwaysAnswer(body: unknown): () => Promise<Response> {
  return () => Promise.resolve(jsonResponse(body));
}

/** A request that never answers, until the probe gives up on it and aborts. */
function hangUntilAborted(_url: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  return new Promise((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
  });
}

/** Lets settled promises run their continuations without moving the clock. */
async function flush(): Promise<void> {
  await vi.advanceTimersByTimeAsync(0);
}

/**
 * Window listeners the store installs. jsdom's window outlives each test's
 * fresh copy of the module, so they are removed by hand after every test.
 */
const installed: Array<[string, EventListenerOrEventListenerObject]> = [];

let fetchMock: FetchMock;
let store: ServerStatusModule;
let seen: ServerStatus[];

/** A fresh copy of the module-level store, with every status it publishes recorded. */
async function loadStore(): Promise<ServerStatusModule> {
  vi.resetModules();
  const fresh = await import("./serverStatus");
  fresh.subscribeServerStatus(() => seen.push(fresh.getServerStatus().status));
  return fresh;
}

/** Starts the probe and lets a first answer that is already settled land. */
async function startedStore(): Promise<ServerStatusModule> {
  const fresh = await loadStore();
  fresh.startServerProbe();
  await flush();
  return fresh;
}

beforeEach(async () => {
  vi.useFakeTimers({ now: Date.UTC(2026, 10, 9, 12, 0, 0) });
  const addEventListener = window.addEventListener.bind(window);
  vi.spyOn(window, "addEventListener").mockImplementation((type, listener, options) => {
    if (listener) installed.push([type, listener]);
    addEventListener(type, listener, options);
  });
  fetchMock = vi.fn<typeof fetch>();
  vi.stubGlobal("fetch", fetchMock);
  seen = [];
  store = await loadStore();
});

afterEach(() => {
  for (const [type, listener] of installed) window.removeEventListener(type, listener);
  installed.length = 0;
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("before the first probe", () => {
  it("reads unknown, and the server render always gets that initial state", () => {
    const initial = { status: "unknown", detail: null, stage: null, run: 0, waited: false };
    expect(store.getServerStatus()).toEqual(initial);
    expect(store.getServerStatusOnServer()).toEqual(initial);
  });
});

describe("a backend that is up", () => {
  it("goes straight to ready and never shows warming, however slowly the probe answers", async () => {
    // Up to the probe's own timeout, slowness is not a failure: a slow answer
    // that says ready is ready. Only a failed probe counts as not ready.
    fetchMock.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(jsonResponse(READY)), PROBE_TIMEOUT_MS - 1)),
    );
    store.startServerProbe();

    await vi.advanceTimersByTimeAsync(PROBE_TIMEOUT_MS - 2);
    expect(store.getServerStatus().status).toBe("unknown");
    await vi.advanceTimersByTimeAsync(1);

    expect(store.getServerStatus()).toEqual({
      status: "ready",
      detail: null,
      stage: "complete",
      run: 1,
      waited: false,
    });
    expect(seen).not.toContain("warming");
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[0]).toBe(READY_URL);
  });

  it("probes once however many times the probe is started", async () => {
    fetchMock.mockImplementation(alwaysAnswer(READY));
    store = await startedStore();
    store.startServerProbe();
    await flush();

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(store.getServerStatus().run).toBe(1);
  });
});

describe("a backend that is restarting", () => {
  it("shows its warm-up stage until it reports ready", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(WARMING)).mockResolvedValueOnce(jsonResponse(READY));
    store = await startedStore();

    expect(store.getServerStatus()).toEqual({
      status: "warming",
      detail: "Loading the race prediction model",
      stage: "model",
      run: 1,
      waited: true,
    });

    await vi.advanceTimersByTimeAsync(PROBE_INTERVAL_MS - 1);
    expect(fetchMock).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(1);

    // `waited` survives into ready: the run did make the reader wait.
    expect(store.getServerStatus()).toEqual({
      status: "ready",
      detail: null,
      stage: "complete",
      run: 1,
      waited: true,
    });
    expect(seen).toEqual(["unknown", "warming", "ready"]);
  });

  it.each([
    ["an error status", () => Promise.resolve(jsonResponse({ detail: "Bad Gateway" }, 502))],
    ["a network error", () => Promise.reject(new TypeError("Failed to fetch"))],
    ["a body that is not JSON", () => Promise.resolve(new Response("<html>starting</html>"))],
    ["a body that is not a report", () => Promise.resolve(jsonResponse(null))],
    ["a report with no ready flag", () => Promise.resolve(jsonResponse({ ready: "yes", stage: "model" }))],
  ])("counts %s as not ready", async (_case, answer) => {
    fetchMock.mockImplementation(answer);
    store = await startedStore();

    expect(store.getServerStatus()).toMatchObject({ status: "warming", stage: null, detail: null, waited: true });
  });

  it("ignores a stage or detail that is not text", async () => {
    fetchMock.mockImplementation(alwaysAnswer({ ready: false, stage: 2, detail: ["model"] }));
    store = await startedStore();

    expect(store.getServerStatus()).toMatchObject({ status: "warming", stage: null, detail: null });
  });

  it("counts a probe with no answer after four seconds as not ready", async () => {
    fetchMock.mockImplementation(hangUntilAborted);
    store.startServerProbe();

    await vi.advanceTimersByTimeAsync(PROBE_TIMEOUT_MS - 1);
    expect(store.getServerStatus().status).toBe("unknown");
    await vi.advanceTimersByTimeAsync(1);

    expect(store.getServerStatus().status).toBe("warming");
    expect(fetchMock.mock.calls[0]?.[1]?.signal?.aborted).toBe(true);
  });
});

describe("a backend that never comes back", () => {
  it("gives up after two minutes and stops probing", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    store = await startedStore();

    await vi.advanceTimersByTimeAsync(GIVE_UP_MS - 1);
    expect(store.getServerStatus().status).toBe("warming");
    await vi.advanceTimersByTimeAsync(1);

    expect(store.getServerStatus()).toMatchObject({ status: "unreachable", stage: null, detail: null, run: 1 });
    const probes = fetchMock.mock.calls.length;
    expect(probes).toBe(GIVE_UP_MS / PROBE_INTERVAL_MS + 1);
    await vi.advanceTimersByTimeAsync(GIVE_UP_MS);
    expect(fetchMock).toHaveBeenCalledTimes(probes);
  });

  it("Try again starts a new run that shows warming at once", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    store = await startedStore();
    await vi.advanceTimersByTimeAsync(GIVE_UP_MS);
    fetchMock.mockReset();
    fetchMock.mockImplementation(hangUntilAborted);

    store.retryServerProbe();

    expect(store.getServerStatus()).toMatchObject({ status: "warming", run: 2, waited: true });
    expect(fetchMock).toHaveBeenCalledOnce();

    fetchMock.mockImplementation(alwaysAnswer(READY));
    await vi.advanceTimersByTimeAsync(PROBE_TIMEOUT_MS + PROBE_INTERVAL_MS);
    expect(store.getServerStatus()).toMatchObject({ status: "ready", run: 2 });
  });

  it("Try again during a run joins it rather than starting another", () => {
    fetchMock.mockImplementation(hangUntilAborted);
    store.startServerProbe();

    store.retryServerProbe();

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(store.getServerStatus()).toMatchObject({ status: "warming", run: 1 });
  });
});

describe("rechecks", () => {
  /** A store whose first run has confirmed the server ready, with the cooldown spent. */
  async function readyStore(): Promise<ServerStatusModule> {
    fetchMock.mockImplementation(alwaysAnswer(READY));
    const ready = await startedStore();
    await vi.advanceTimersByTimeAsync(RECHECK_COOLDOWN_MS);
    fetchMock.mockClear();
    return ready;
  }

  it("does nothing before the probe has started", async () => {
    store.recheckServer();
    await flush();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(store.getServerStatus().run).toBe(0);
  });

  it("does nothing while offline", async () => {
    store = await readyStore();
    vi.spyOn(window.navigator, "onLine", "get").mockReturnValue(false);

    store.recheckServer();

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("waits ten seconds after a ready verdict, then probes without flashing warming", async () => {
    fetchMock.mockImplementation(alwaysAnswer(READY));
    store = await startedStore();
    await vi.advanceTimersByTimeAsync(RECHECK_COOLDOWN_MS - 1);

    store.recheckServer();
    expect(fetchMock).toHaveBeenCalledOnce();

    await vi.advanceTimersByTimeAsync(1);
    store.recheckServer();
    await flush();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(store.getServerStatus()).toMatchObject({ status: "ready", run: 2, waited: false });
    expect(seen).not.toContain("warming");
  });

  it("shows warming when the server went away, and ready once it is back", async () => {
    store = await readyStore();
    fetchMock.mockResolvedValueOnce(jsonResponse(WARMING)).mockResolvedValueOnce(jsonResponse(READY));

    store.recheckServer();
    await flush();
    expect(store.getServerStatus()).toMatchObject({ status: "warming", stage: "model", run: 2 });

    await vi.advanceTimersByTimeAsync(PROBE_INTERVAL_MS);
    expect(store.getServerStatus()).toMatchObject({ status: "ready", run: 2, waited: true });
  });

  it("probes again when the device comes back online", async () => {
    store = await readyStore();

    window.dispatchEvent(new Event("online"));

    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("probes again when the page comes back from the back/forward cache", async () => {
    store = await readyStore();

    window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: false }));
    expect(fetchMock).not.toHaveBeenCalled();

    window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("does not probe when a tab comes back from the background", async () => {
    // The backend no longer sleeps when idle, so a long-hidden tab is no sign of
    // a restart. A failed request still asks for a recheck (see `fetcher.ts`).
    store = await readyStore();
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(30 * 60_000);
    visibility.mockReturnValue("visible");
    document.dispatchEvent(new Event("visibilitychange"));
    await flush();

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("subscriptions", () => {
  it("notify on every change until unsubscribed, with a stable snapshot in between", async () => {
    const listener = vi.fn();
    const unsubscribe = store.subscribeServerStatus(listener);
    expect(store.getServerStatus()).toBe(store.getServerStatus());

    fetchMock.mockImplementation(alwaysAnswer(READY));
    store.startServerProbe();
    await flush();
    const calls = listener.mock.calls.length;
    expect(calls).toBeGreaterThan(0);

    unsubscribe();
    await vi.advanceTimersByTimeAsync(RECHECK_COOLDOWN_MS);
    store.recheckServer();
    await flush();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(listener).toHaveBeenCalledTimes(calls);
  });
});
