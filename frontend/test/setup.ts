import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "./msw/server";

// An unmocked request is a test bug (or a real network call), never a pass.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

afterEach(() => {
  // Vitest runs without globals, so Testing Library cannot register this itself.
  cleanup();
  server.resetHandlers();
});

afterAll(() => server.close());
