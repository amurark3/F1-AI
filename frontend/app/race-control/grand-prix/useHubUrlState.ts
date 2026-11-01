"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

import { hubQuery, readHubParams, type HubSelection } from "./hubNavigation";

export interface HubUrl extends HubSelection {
  update: (changes: Partial<HubSelection>) => void;
}

/**
 * The hub's selection before the URL can be read — the server render, which
 * shows the default round and lets the calendar pick the section.
 */
export const DEFAULT_HUB_URL: HubUrl = { round: null, tab: null, view: null, update: () => undefined };

/** The selection held in the URL, and a way to change it without a scroll jump. */
export function useHubUrlState(): HubUrl {
  const search = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const selection = useMemo(() => readHubParams(new URLSearchParams(search.toString())), [search]);

  const update = useCallback(
    (changes: Partial<HubSelection>) => {
      const query = hubQuery({ ...selection, ...changes });
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [selection, pathname, router],
  );

  return useMemo(() => ({ ...selection, update }), [selection, update]);
}
