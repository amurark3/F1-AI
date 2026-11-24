import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as StoreModule from "./serverStatus";

type Store = typeof StoreModule;

const READY = { ready: true, stage: "ready", detail: "Ready" };
const stageAnswer = (stage: string, detail = `Doing ${stage}`) => ({ ready: false, stage, detail });

let answers: unknown[];
let fetchMock: ReturnType<typeof vi.fn>;
let handlers: Record<string, (event?: unknown) => void>;
let store: Store;

/** Each probe takes the next queued answer: a body, `"fail"` (network error), `"http"` (500) or `"junk"`. */
function respond(...next: unknown[]): void {
  answers = next;
}

beforeEach(async () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-23T12:00:00Z"));
  handlers = {};
  vi.spyOn(window, "addEventListener").mockImplementation(((type: string, handler: (event?: unknown) => void) => {
    handlers[type] = handler;
  }) as typeof window.addEventListener);
  answers = [];
  fetchMock = vi.fn(() => {
    const next = answers.length > 1 ? answers.shift() : answers[0];
    if (next === "fail") return Promise.reject(new TypeError("network"));
    if (next === "http") return Promise.resolve({ ok: false });
    if (next === "badjson") return Promise.resolve({ ok: true, json: () => Promise.reject(new SyntaxError("bad")) });
    return Promise.resolve({ ok: true, json: () => Promise.resolve(next === "junk" ? { ready: "yes" } : next) });
  });
  vi.stubGlobal("fetch", fetchMock);
  vi.resetModules();
  store = await import("./serverStatus");
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const tick = (ms: number) => vi.advanceTimersByTimeAsync(ms);
const phase = () => store.noticePhase(store.getServerStatus());

describe("lightsFor", () => {
  it("lights 1 to 5 by the stage in progress", () => {
    expect(["pending", "database", "model", "season", "store"].map((stage) => store.lightsFor(stage, false))).toEqual([
      1, 2, 3, 4, 5,
    ]);
  });

  it("lights all five when ready", () => {
    expect(store.lightsFor("ready", true, 2)).toBe(5);
  });

  it("keeps the count reached on an unknown stage or no answer, and never lowers it", () => {
    expect(store.lightsFor("surprise", false, 3)).toBe(3);
    expect(store.lightsFor(null, false, 4)).toBe(4);
    expect(store.lightsFor("database", false, 4)).toBe(4);
  });

  it("lights one while nothing has answered yet", () => {
    expect(store.lightsFor(null, false)).toBe(1);
    expect(store.lightsFor("surprise", false)).toBe(1);
  });
});

describe("parseReadiness", () => {
  it("accepts the documented shape and nothing else", () => {
    expect(store.parseReadiness(READY)).toEqual(READY);
    expect(store.parseReadiness(null)).toBeNull();
    expect(store.parseReadiness("ready")).toBeNull();
    expect(store.parseReadiness({ ready: "yes", stage: "x", detail: "y" })).toBeNull();
    expect(store.parseReadiness({ ready: true, stage: 1, detail: "y" })).toBeNull();
    expect(store.parseReadiness({ ready: true, stage: "x" })).toBeNull();
  });
});

describe("the probe", () => {
  it("shows nothing for a server that is up", async () => {
    respond(READY);
    store.startServerProbe();
    await tick(0);

    expect(store.getServerStatus()).toMatchObject({ status: "ready", waited: false, lit: 5 });
    expect(phase()).toBeNull();
    await tick(60_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not call a slow answer a restart", async () => {
    fetchMock.mockReturnValue(new Promise(() => undefined));
    store.startServerProbe();
    await tick(store.PROBE_TIMEOUT_MS + 1);

    expect(store.getServerStatus().status).toBe("unknown");
    expect(phase()).toBeNull();
  });

  it("fills the lights by stage, then plays back online once for a run that waited", async () => {
    respond(stageAnswer("pending"), stageAnswer("model"), stageAnswer("store"), READY);
    store.startServerProbe();
    await tick(0);
    expect(store.getServerStatus()).toMatchObject({ status: "warming", lit: 1, detail: "Doing pending" });
    expect(phase()).toBe("warming");

    await tick(3000);
    expect(store.getServerStatus()).toMatchObject({ lit: 3, stage: "model" });
    await tick(3000);
    expect(store.getServerStatus().lit).toBe(5);
    await tick(3000);

    expect(store.getServerStatus()).toMatchObject({ status: "ready", lit: 5, waited: true });
    expect(phase()).toBe("launching");
    await tick(store.LAUNCH_DURATION_MS);
    expect(phase()).toBeNull();
  });

  it("keeps the count through failed, malformed and unknown answers", async () => {
    respond(stageAnswer("season"), "fail", "http", "junk", "badjson", stageAnswer("other"), READY);
    store.startServerProbe();
    await tick(0);
    expect(store.getServerStatus().lit).toBe(4);

    for (let attempt = 0; attempt < 4; attempt += 1) {
      await tick(3000);
      expect(store.getServerStatus()).toMatchObject({ status: "warming", lit: 4, detail: "Doing season" });
    }
    await tick(3000);
    expect(store.getServerStatus()).toMatchObject({ lit: 4, stage: "other" });
    await tick(3000);
    expect(store.getServerStatus().status).toBe("ready");
  });

  it("lights one when the very first probe fails", async () => {
    respond("fail");
    store.startServerProbe();
    await tick(0);

    expect(store.getServerStatus()).toMatchObject({ status: "warming", lit: 1, detail: null });
  });

  it("gives up after 120 seconds, and Dismiss hides it for the run", async () => {
    respond("fail");
    store.startServerProbe();
    await tick(store.GIVE_UP_MS - 3000);
    expect(phase()).toBe("warming");
    await tick(6000);

    expect(store.getServerStatus().status).toBe("unreachable");
    expect(phase()).toBe("unreachable");
    store.dismissServerNotice();
    expect(phase()).toBeNull();
  });

  it("Try again probes at once and keeps the lights reached", async () => {
    respond(stageAnswer("database"), "fail");
    store.startServerProbe();
    await tick(store.GIVE_UP_MS + 3000);
    expect(phase()).toBe("unreachable");
    const runBefore = store.getServerStatus().run;

    respond(READY);
    store.retryServerProbe();
    expect(store.getServerStatus()).toMatchObject({ status: "warming", lit: 2, run: runBefore + 1 });
    await tick(0);
    expect(phase()).toBe("launching");
  });

  it("starts again for a restart, from one light, once the ready cooldown has passed", async () => {
    respond(READY);
    store.startServerProbe();
    await tick(0);

    respond("fail");
    store.recheckServer();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await tick(10_000);
    store.recheckServer();
    store.recheckServer();
    await tick(0);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(store.getServerStatus()).toMatchObject({ status: "warming", lit: 1 });
  });

  it("ignores rechecks before the first run and while offline", async () => {
    store.recheckServer();
    expect(fetchMock).not.toHaveBeenCalled();

    respond(READY);
    store.startServerProbe();
    store.startServerProbe();
    await tick(11_000);
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    store.recheckServer();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("rechecks when the page comes back online or from the back/forward cache", async () => {
    respond(READY);
    store.startServerProbe();
    await tick(11_000);

    handlers.pageshow({ persisted: false });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    handlers.pageshow({ persisted: true });
    await tick(11_000);
    handlers.online();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(handlers.visibilitychange).toBeUndefined();
  });
});

describe("the store", () => {
  it("notifies subscribers until they unsubscribe, and is blank on the server", async () => {
    const listener = vi.fn();
    const unsubscribe = store.subscribeServerStatus(listener);
    respond(READY);
    store.startServerProbe();
    await tick(0);
    expect(listener).toHaveBeenCalled();

    const calls = listener.mock.calls.length;
    unsubscribe();
    store.dismissServerNotice();
    expect(listener).toHaveBeenCalledTimes(calls);
    expect(store.getServerStatusOnServer()).toMatchObject({ status: "unknown", lit: 0 });
  });
});
