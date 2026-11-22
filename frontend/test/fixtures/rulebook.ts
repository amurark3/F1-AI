/**
 * The Rulebook search's four payloads for "When is a driver required to start from the pit lane?"
 * (2026), as `POST /api/race-control/rulebook/search` serves them.
 *
 * Captured on 2026-11-22 by calling `search_rulebook` in one script, with no live model and
 * no database. The FIA store was seeded with every R19 document (`backend/tests/fixtures/
 * fia_documents`). The passages are stubbed as the search's top three: page 29 of the 2026
 * Sporting Regulations (Iss 04), split with the ingest's splitter settings, starting at the
 * chunk holding "B3.5.3 When deemed". The article matching, the keyword search and the
 * documents are real.
 *
 * - `answered_ai`: a hand-written stand-in for a model reply (it passes `check_reply`).
 * - `answered_computed`: the same question with no engine key, so the computed text stands in.
 * - `keyword`: the rule index off (`ENABLE_LOCAL_MODELS` false); decisions found by the question's words.
 * - `unavailable`: the same with the FIA document store failing.
 */

import type { RulebookSearched, RulebookUnavailable } from "@/app/race-control/rulebook/rulebookModel";

import raw from "./rulebook-2026.json";

export const RULEBOOK_2026 = raw as unknown as {
  answered_ai: RulebookSearched;
  answered_computed: RulebookSearched;
  keyword: RulebookSearched;
  unavailable: RulebookUnavailable;
};
