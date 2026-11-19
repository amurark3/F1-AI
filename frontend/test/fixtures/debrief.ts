/**
 * The 2026 Mexico City Grand Prix (round 19) debrief, as the four endpoints serve it.
 *
 * Captured on 2026-11-18 by calling the backend's own builders (`build_race_debrief`,
 * `build_debrief_laps`, `build_debrief_penalties`, `build_debrief_overtakes`) for
 * (2026, 19) in one script, on f1db v2026.20.0. The FIA store was seeded with every
 * R19 document (`backend/tests/fixtures/fia_documents`, so the final classification is
 * document 86 and the penalties and grid come from the FIA's own text). OpenF1 was read
 * live. `summary` and `penalties` are therefore the real payloads; `laps` and `overtakes`
 * are OpenF1's rows as of the capture.
 */

import type {
  DebriefLaps,
  DebriefOvertakes,
  DebriefPenalties,
  DebriefSummary,
} from "@/app/race-control/debriefs/debriefTypes";

import raw from "./debrief-2026-r19.json";

export const DEBRIEF_R19 = raw as unknown as {
  summary: DebriefSummary;
  laps: DebriefLaps;
  penalties: DebriefPenalties;
  overtakes: DebriefOvertakes;
};
