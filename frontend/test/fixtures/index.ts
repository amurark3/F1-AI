/**
 * Real backend responses, for unit, component and e2e tests.
 *
 * Captured from the local backend (uvicorn with `DATABASE_URL` and `SENTRY_DSN`
 * blank) on 2026-11-02 (01:46 UTC on 3 Nov), on f1db v2026.19.0, which
 * publishes round 19 (Mexico City), so the table is confirmed, not provisional.
 *
 * - `teams-2026.json`: `GET /api/race-control/teams/2026`. Each team's
 *   `strategy_tendency`, `standing_profile`, `recent_form` and `pace_profile`
 *   are dropped (the championship hub reads none of them); the rest is as served.
 * - `profiles-directory-2026.json`: `GET /api/profiles/2026/directory`, as served.
 * - `ready.json`: `GET /api/ready`, kept to the `ready`, `stage` and `detail`
 *   fields the warm-up probe reads.
 *
 * Re-capture rather than hand-edit: a fixture is evidence of what the backend
 * sends, never an invented case.
 */
import type { SeasonDirectory } from "@/app/race-control/profiles/profilesModel";
import type { TeamsResponse } from "@/app/race-control/teams/teamsModel";

import directory2026 from "./profiles-directory-2026.json";
import ready from "./ready.json";
import teams2026 from "./teams-2026.json";

// JSON imports widen string unions (`role: string`), hence the assertions.
export const TEAMS_2026 = teams2026 as TeamsResponse;
export const DIRECTORY_2026 = directory2026 as SeasonDirectory;
export const READY = ready;
