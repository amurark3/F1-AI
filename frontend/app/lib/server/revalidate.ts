/**
 * How long each class of backend data stays fresh in Next's data cache.
 *
 * Grouped by how fast the underlying data actually moves, not by which page
 * consumes it — several pages share the schedule and standings, and they should
 * all hit the same cache entry.
 */
export const REVALIDATE = {
  /**
   * Historical results. Immutable once a season closes.
   *
   * An hour rather than a day, despite the data never changing. ISR serves the
   * cached page instantly either way — the window only sets how often it
   * regenerates in the background — so a long one buys nothing but bounds how
   * long a page built during a backend outage keeps serving its error state.
   */
  ARCHIVE: 3_600,
  /** Race calendar. Fixed at season start, revised occasionally. */
  SCHEDULE: 3_600,
  /** Entry lists. Change on driver moves, not on race day. */
  ENTRY_LIST: 3_600,
  /** Championship tables and post-race debriefs. Move once per race weekend. */
  STANDINGS: 900,
  /** Command-centre overview and rival intel. Shift during a session. */
  OVERVIEW: 300,
  /** Model output. Recomputed as practice and qualifying land. */
  PREDICTIONS: 300,
  /**
   * The starting grid. Fixed once a round is run, but during the round in
   * question it moves from "not set" to provisional to official within a day.
   */
  GRID: 300,
  /**
   * Session classifications and race strategy. Both are fixed once a weekend
   * is complete, and absent until then.
   */
  SESSION_RESULTS: 300,
} as const;
