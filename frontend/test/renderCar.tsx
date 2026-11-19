import { act } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Suspense, type ComponentType } from "react";

import type { CarSectionProps } from "@/app/race-control/power-units/[car]/useCar";
import { DIRECTORY_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

export interface RenderCarOptions {
  segment?: string;
  /** What the browser's own fetch answers when it asks again; defaults to the seed. */
  live?: unknown;
  /** Seed as a promise that never settles: the section stays on its boundary. */
  never?: boolean;
}

/** Renders one section of the car page, seeded as the server would seed it. */
export async function renderCar(
  Section: ComponentType<CarSectionProps>,
  seed: unknown,
  { segment = "6", live = seed, never = false }: RenderCarOptions = {},
) {
  server.use(
    http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
    http.get(apiUrl("/api/race-control/power-units/2026"), () => HttpResponse.json(live as never)),
  );
  const promise = (never ? new Promise(() => undefined) : Promise.resolve(seed)) as CarSectionProps["seed"];
  let view!: ReturnType<typeof renderWithProviders>;
  await act(() => {
    view = renderWithProviders(
      <Suspense fallback={<p>loading</p>}>
        <Section year={2026} segment={segment} seed={promise} />
      </Suspense>,
    );
    return Promise.resolve();
  });
  return view;
}
