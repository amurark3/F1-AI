import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "./msw/server";

// An unmocked request is a test bug (or a real network call), never a pass.
// MSW 3 renamed `onUnhandledRequest` to `onUnhandledFrame` (it now covers
// WebSocket connections too); the old key is ignored, not rejected at runtime.
beforeAll(() => server.listen({ onUnhandledFrame: "error" }));

afterEach(() => {
  // Vitest runs without globals, so Testing Library cannot register this itself.
  cleanup();
  server.resetHandlers();
});

/**
 * Requests still in flight when a file ends. Files in a worker share one
 * environment (`vmThreads`), and closing MSW under a live request leaves the
 * next file's `fetch` unintercepted: its mocks never answer. So a file waits for
 * its requests to end first, capped for handlers that deliberately never resolve.
 */
const inFlight = new Set<string>();
const DRAIN_CAP_MS = 1_000;
server.events.on("request:start", ({ requestId }) => inFlight.add(requestId));
server.events.on("request:end", ({ requestId }) => inFlight.delete(requestId));

async function drainRequests(): Promise<void> {
  const deadline = Date.now() + DRAIN_CAP_MS;
  while (inFlight.size > 0 && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}

afterAll(async () => {
  await drainRequests();
  server.close();
});
