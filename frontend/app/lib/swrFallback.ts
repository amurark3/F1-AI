/**
 * Builds the SWR options that seed a hook with server-rendered data.
 *
 * Passing `fallbackData: undefined` is not the same as omitting it — SWR treats
 * the key as present and skips its loading state — so the property has to be
 * absent entirely when the server fetch came back empty. Spreading the result of
 * this helper keeps that conditional out of every call site.
 *
 * When seeded, `revalidateOnMount` stays on: the server payload paints
 * immediately and SWR refreshes it in the background, so a cached render never
 * leaves stale numbers on screen.
 */
export function seededWith<T>(initial: T | null | undefined): { fallbackData?: T } {
  return initial == null ? {} : { fallbackData: initial };
}

/**
 * Whether a hook has nothing to show yet.
 *
 * `fallbackData` seeds `data` but does not populate SWR's cache, so SWR still
 * reports `isLoading: true` for a key it has not fetched — on the server that
 * is every key. Gating spinners and disabled controls on the raw flag would
 * ship server-rendered HTML that looks like it is still loading despite already
 * holding the data.
 *
 * It is the better predicate on the client too: a background revalidation
 * should not blank out or disable a control that already has content.
 */
export function awaitingFirstData(isLoading: boolean, hasData: boolean): boolean {
  return isLoading && !hasData;
}
