/**
 * The 2026 Mexico City Grand Prix (round 19) as `/api/race-control/rewind/2026/19` serves it.
 *
 * Built 2026-11-23 by `build_race_rewind(2026, 19)` on the R19 fixtures (OpenF1 captured
 * 2026-11-23, FIA documents as fia.com served them, f1db test rows). Real data, nothing hand-edited.
 */

import type { RaceRewind } from "@/app/race-control/rewind/rewindTypes";

import raw from "./race-rewind-2026-r19.json";

export const REWIND_R19 = raw as unknown as RaceRewind;
