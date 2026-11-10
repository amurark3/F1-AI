import { render, type RenderOptions, type RenderResult } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { SWRConfig } from "swr";

import type { ReactElement, ReactNode } from "react";

/**
 * The providers a component gets in the app, set up for tests.
 *
 * Each render gets its own SWR cache, so one test's responses never leak into
 * the next, and a failed request is not retried behind the test's back.
 */
export function TestProviders({ children }: { children: ReactNode }) {
  return (
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}>
      {children}
    </SWRConfig>
  );
}

export interface RenderWithProvidersResult extends RenderResult {
  /** A user-event session bound to this render. */
  user: UserEvent;
}

/** Renders `ui` inside the app's providers, with a user-event session. */
export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper">,
): RenderWithProvidersResult {
  const user = userEvent.setup();
  return { user, ...render(ui, { wrapper: TestProviders, ...options }) };
}
