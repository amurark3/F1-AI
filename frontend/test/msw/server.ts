import { setupServer } from "msw/node";

import { API_BASE } from "@/app/constants/api";

/**
 * The mock backend for unit and component tests.
 *
 * It starts with no handlers: each test declares the responses it relies on
 * with `server.use(...)`, and `test/setup.ts` fails any request nobody
 * declared, so a test can never reach a real network.
 */
export const server = setupServer();

/** The URL the app requests for a backend path, e.g. `apiUrl("/api/ready")`. */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}
