import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as BackendModule from "./backend";

type Backend = typeof BackendModule;

const json = (body: unknown, status = 200): Response => new Response(JSON.stringify(body), { status });

/** A fresh module, so the env-derived constants are read again. */
async function loadBackend(env: Record<string, string> = {}): Promise<Backend> {
  vi.resetModules();
  vi.stubEnv("API_URL", "");
  vi.stubEnv("NEXT_PUBLIC_API_URL", "");
  vi.stubEnv("NEXT_PHASE", "");
  for (const [key, value] of Object.entries(env)) vi.stubEnv(key, value);
  return import("./backend");
}

describe("fetchFromBackend", () => {
  const fetchMock = vi.fn<typeof fetch>();
  let warn: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", fetchMock);
    warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it("returns the parsed body, uncached when no revalidate is given", async () => {
    const { fetchFromBackend } = await loadBackend();
    fetchMock.mockResolvedValue(json({ ok: 1 }));

    await expect(fetchFromBackend("/api/x")).resolves.toEqual({ ok: 1 });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/x",
      expect.objectContaining({ cache: "no-store", next: undefined }),
    );
  });

  it("hands Next the revalidate window and tags", async () => {
    const { fetchFromBackend } = await loadBackend();
    fetchMock.mockImplementation(() => Promise.resolve(json([1])));

    await fetchFromBackend("/api/x", { revalidate: 60, tags: ["a", "b"] });
    await fetchFromBackend("/api/y", { revalidate: 60 });

    expect(fetchMock.mock.calls[0][1]).toMatchObject({ next: { revalidate: 60, tags: ["a", "b"] }, cache: undefined });
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ next: { revalidate: 60, tags: undefined } });
  });

  it("prefers the internal API_URL for server renders", async () => {
    const { fetchFromBackend } = await loadBackend({ API_URL: " http://internal:9000 " });
    fetchMock.mockResolvedValue(json({}));

    await fetchFromBackend("/api/x");

    expect(fetchMock.mock.calls[0][0]).toBe("http://internal:9000/api/x");
  });

  it("falls back to the public base when API_URL is blank", async () => {
    const { fetchFromBackend } = await loadBackend({ NEXT_PUBLIC_API_URL: "https://api.example.com" });
    fetchMock.mockResolvedValue(json({}));

    await fetchFromBackend("/api/x");

    expect(fetchMock.mock.calls[0][0]).toBe("https://api.example.com/api/x");
  });

  it("gives up on a status that retrying will not fix", async () => {
    const { fetchFromBackend } = await loadBackend();
    fetchMock.mockResolvedValue(json({}, 404));

    await expect(fetchFromBackend("/api/x")).resolves.toBeNull();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("/api/x unavailable (HTTP 404)"));
  });

  it("retries a throttled response after a backoff and returns the retry", async () => {
    const { fetchFromBackend } = await loadBackend();
    fetchMock.mockResolvedValueOnce(json({}, 429)).mockResolvedValueOnce(json({ seeded: true }));

    const result = fetchFromBackend("/api/x");
    await vi.advanceTimersByTimeAsync(400);

    await expect(result).resolves.toEqual({ seeded: true });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("stops after three attempts", async () => {
    const { fetchFromBackend } = await loadBackend();
    fetchMock.mockImplementation(() => Promise.resolve(json({}, 503)));

    const result = fetchFromBackend("/api/x");
    await vi.advanceTimersByTimeAsync(400 + 800);

    await expect(result).resolves.toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("HTTP 503"));
  });

  it.each([
    ["an Error", new Error("connection refused"), "connection refused"],
    ["a non-Error value", "boom", "unknown error"],
  ])("retries when the request throws %s", async (_name, thrown, reason) => {
    const { fetchFromBackend } = await loadBackend();
    fetchMock.mockRejectedValue(thrown);

    const result = fetchFromBackend("/api/x");
    await vi.advanceTimersByTimeAsync(400 + 800);

    await expect(result).resolves.toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining(`(${reason})`));
  });

  it("does not start with a spent budget", async () => {
    const { fetchFromBackend } = await loadBackend();

    await expect(fetchFromBackend("/api/x", { timeoutMs: 0 })).resolves.toBeNull();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("budget exhausted"));
  });

  it("does not wait for a retry that cannot fit in the budget", async () => {
    const { fetchFromBackend } = await loadBackend();
    fetchMock.mockResolvedValue(json({}, 503));

    await expect(fetchFromBackend("/api/x", { timeoutMs: 300 })).resolves.toBeNull();

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  describe("deadline", () => {
    const hang = () =>
      fetchMock.mockImplementation(
        (_url, init) =>
          new Promise((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
          }),
      );

    it("aborts a hung request after 10 s", async () => {
      const { fetchFromBackend } = await loadBackend();
      hang();

      const result = fetchFromBackend("/api/x");
      await vi.advanceTimersByTimeAsync(10_000);

      await expect(result).resolves.toBeNull();
      expect(warn).toHaveBeenCalledWith(expect.stringContaining("(timed out)"));
    });

    it("allows 25 s while `next build` generates pages", async () => {
      const { fetchFromBackend } = await loadBackend({ NEXT_PHASE: "phase-production-build" });
      hang();

      const result = fetchFromBackend("/api/x");
      await vi.advanceTimersByTimeAsync(10_000);
      expect(warn).not.toHaveBeenCalled();
      await vi.advanceTimersByTimeAsync(15_000);

      await expect(result).resolves.toBeNull();
      expect(warn).toHaveBeenCalledWith(expect.stringContaining("(timed out)"));
    });
  });
});
