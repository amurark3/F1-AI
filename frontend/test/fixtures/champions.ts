import type { ChampionsResponse, LatestChampion, SeasonDetail } from "@/app/lib/server/champions";

import champions2026 from "./champions-2026.json";

/**
 * The Champions payloads as the backend serves them for f1db v2026.20.0
 * (champions-2026.json, captured 2026-11-18 by calling `list_champions`,
 * `latest_champion` and `get_season_detail` on the real database). Antonelli
 * clinched in round 19 of 23; f1db holds rounds 1-20. Tests derive variants
 * (an open title, a repeat champion) by spreading these and say so.
 */
export const CHAMPIONS = {
  list: { seasons: champions2026.list } as ChampionsResponse,
  latest: champions2026.latest as LatestChampion,
  season2026: champions2026.season_2026 as SeasonDetail,
  season1957: champions2026.season_1957 as SeasonDetail,
};
