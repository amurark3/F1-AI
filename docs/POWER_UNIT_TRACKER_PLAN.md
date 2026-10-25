# Power Unit Usage Tracker — Research & Plan

_Researched 2026-10-23, during the US GP weekend. **Built 2026-10-24** — see "As built" directly below; the
sections after it are the original research, kept for its verified examples._

Goal: for each driver, a screen showing the power-unit (PU) elements they are allowed, how many they have
used, the Grand Prix where each new element arrived, and the grid penalty it cost them there.

---

## As built (2026-10-24)

What changed from the plan below, and why:

- **Keyed by car number, with the driver beside it.** Article B8.2.7 makes usage belong to the car. Each car
  lists everyone who raced it, and the round-by-round story shows stand-ins ("driven by Liam Lawson" at Monza).
- **Seat attribution uses the document's own printed team and number, not f1db's line-up.** Azerbaijan's Friday
  report still printed Monza's line-up ("30 Red Bull … Lawson") with Red Bull #6's counts, while Hadjar raced
  that weekend. The two questions are therefore answered separately:
  - which car a document row is about comes from the printed label;
  - who raced the car comes from f1db.
- **Allowances live in Supabase, not code** (`power_unit_allowances`). The ingest job keeps each element at the
  latest figure the FIA's reports state ("of the four (4) new … allowed"), with the document that stated it.
  `scripts/power_unit_allowances.py` pins a value by hand, and a pinned value is never overwritten. The screen
  shows each allowance's source, and warns when the FIA's latest statement disagrees.
  - Reports from early 2026 quote the B8.2.2 base (e.g. PU-CE 2), later ones the total (3). The latest
    statement wins.
- **Withdrawn and rescinded documents are kept but not counted**, and each is listed on the screen with its
  reason. The cases handled:
  - removed from the FIA event page;
  - marked withdrawn or rescinded on the page;
  - taken back by a later document ("Document 41 is rescinded", "replaces Document 37");
  - reissued as "Corrected …".
  - A page that is cut short or unreadable never withdraws anything.
  - The scheduled job re-reads every event page once a day, which catches a rescission after its weekend.
- **"Last checked" on screen.** Every ingest run, including failures, writes `power_unit_ingest_status`. The
  screen shows last checked, last change and the newest FIA document, and flags a check more than 26 hours old.
- **One endpoint**, `GET /api/race-control/power-units/{year}`, serves both screens and the AI Engineer tool
  `get_power_unit_usage`.
- **Screens:**
  - `/race-control/power-units`: allocation matrix, stewards' decision log, allowances, provenance.
  - `/race-control/power-units/[car]`: element ledger with per-unit inspector, season timeline, weekend cards.
- **Not built:** the GridPenalties reason column in the Grand Prix Hub (§5.3), iOS (out of scope by request),
  and seasons before 2026.

---

## 1. Short answer

- **Is the data available?** Not from anything the app uses today, but yes from the FIA.
  - f1db has grid penalties (places, back of grid, pit-lane starts) but not the offence. `app/data/f1db_grid.py`
    and `GridPenalties.tsx` already say so.
  - FastF1, OpenF1 and Jolpica have nothing on PU usage.
  - The FIA publishes it as PDFs every race weekend. These parse cleanly with `pypdf`, which is already pinned
    in `requirements-ingest.txt`.
- **How many are allowed (2026)?** ICE 4 · TC 4 · EXH 4 · MGU-K 3 · ES 3 · PU-CE 3 · PU-ANC 6 per driver (§3).
- **Everything the screen needs exists:**

  | Need | Source |
  |---|---|
  | Allowance | Regulations |
  | Used count | FIA Technical Delegate (TD) report |
  | Event where each new element arrived | FIA TD report |
  | Penalty for it | Stewards' decision |
  | How it landed on the grid | f1db |

- **Main catch:** usage belongs to the **seat**, not the person (B8.2.7). A stand-in uses the original driver's
  allocation (§4, case 2).

## 2. Sources

### 2.1 FIA document types

All three were checked on the 2026 Singapore, Italian and US GPs.

| Document | Published | What it gives | Example |
|---|---|---|---|
| TD report: "PU Elements used per Driver up to now" | Friday, once per event | Each driver's cumulative count per element going into the weekend | [Singapore](https://www.fia.com/system/files/decision-document/2026_singapore_grand_prix_-_pu_elements_used_per_driver_up_to_now.pdf) |
| TD report: "New PU elements for this Competition" | One or more per event (`…competition.pdf`, `…_0.pdf`, `…_1.pdf`; Monza had three) | For each new element fitted at this event: car, driver, team, "previously used" count, and the allowance in words ("the sixth (6th) of the four (4) new exhaust sets allowed") | [US GP](https://www.fia.com/system/files/decision-document/2026_united_states_grand_prix_-_new_pu_elements_for_this_competition.pdf) |
| Stewards' decision: "Infringement – Car N – …PU element(s)…" | Per offending driver, sometimes several per event | Element ordinals, the session first used, the decision (grid drop of N, or pit lane), the 10-vs-5 reasoning, articles cited | [Russell, Singapore](https://www.fia.com/system/files/decision-document/2026_singapore_grand_prix_-_infringement_-_car_63_-_changes_to_pu_elements.pdf) |

Two lookalikes are not useful:

- "Power Unit Information" covers per-circuit energy and overtake limits.
- The provisional and final grid PDFs duplicate what f1db already has.

**How to find the documents.** Start at `fia.com/documents/championships/fia-formula-one-world-championship-14`.
That index links to each season page (2026 is `season-2026-2072`). Read the season id from the index rather than
hardcoding it. The season page links to the event pages, and each event page links to
`/system/files/decision-document/*.pdf`. `robots.txt` sets `Crawl-delay: 10` and does not disallow these paths.

**Stewards' document titles vary.** Seen so far: `changes_to_pu_elements`, `change_to_pu_elements`,
`additional_changes_to_pu_elements`, `pu_element`, `pu_elements`,
`pu_element_and_changes_made_during_parc_ferme` and `pu_elements_changed_during_parc_ferme`. Use the URL slug
only as a pre-filter. Classify by content: the text "The following Power Unit elements has/have been used". A
parc fermé decision with no PU element (Lawson, Monza, doc 57) must be rejected.

### 2.2 Parsing quirks in pypdf 6.19 output

- **Split words.** Names and teams break mid-word: "Geor ge Russell", "Racin g Bulls", "Gasl y",
  "Hülkenber g". Match rows on **car number + team**, never on the name text.
- **Split headers and changing columns.** Column headers break across lines ("MGU\n-K", "PU-\nCE"). Read the
  element legend from each document instead of assuming the columns. The 2025 documents use a different set:
  ICE, TC, MGU-H, MGU-K, ES, CE, EX.
- **Wording varies.** "in compliance" vs "in conformity"; "has" vs "have been used"; "Drop of N grid positions
  in/for the next Race". The template says "the above drivers" even when only one driver is listed.
- **Pit-lane outcomes.** One decision can combine a PU element with parc fermé breaches. The outcome is
  "Required to start the Race from the pit lane … The grid drop penalty is redundant". Store the outcome and the
  nominal places ("normally carries a 5 grid place penalty") separately.
- **Event identity.** Three places identify the event:
  - The header gives the name and date range ("09 - 11 October 2026").
  - The enclosure name gives the round ("17 SIN GP 26 TDR1.pdf").
  - The new-elements text gives the round as a word ("eighteenth Competition").

  Match to f1db by date and name, and use the round number as a cross-check.
- **Locating text.** Find content by its anchor text, not by page number. Every document has a cover page and
  then a body.

### 2.3 What f1db adds

The `race_data` rows of type `STARTING_GRID_POSITION` give the grid outcome:

- the qualifying position
- the applied penalty, as a number of places or `SFB` (start from back)
- `PL` for a pit-lane start

f1db publishes a round only after it is complete, so this lags the stewards' decision by a day or more. Handle
that the way `race_grid.py` already handles its provisional state.

## 3. Rules

Source: 2026 F1 Regulations, Section B, Issue 04, 10 Dec 2025, in `backend/data/raw/2026/`.

| Element | B8.2.2 base | 2026 (B8.2.3a adds 1) | Confirmed by FIA report wording |
|---|---|---|---|
| ICE | 3 | **4** | "four (4) new internal combustion engines" |
| TC | 3 | **4** | "four (4) new turbochargers" |
| EXH | 3 | **4** | "four (4) new exhaust sets" |
| MGU-K | 2 | **3** | Russell's 4th MGU-K was penalised |
| ES | 2 | **3** | "three (3) new energy store units" |
| PU-CE | 2 | **3** | "three (3) new control electronics units" |
| PU-ANC | 5 | **6** | "six (6) new power unit ancillary components" |

- **B8.2.3b (first-year bonus).** A PU manufacturer in its first year of supply gets one extra of each element.
  From 2027 this is the only bonus: Appendix B6 lists no B8.2 change for 2027–29. So the allowance depends on
  the season **and** the manufacturer. Re-check when the 2027 regulations are published.
- **B8.2.8 (penalties).**
  - The first extra element of each type costs 10 grid places.
  - Each later extra element of that type costs 5.
  - Penalties are cumulative and apply at the first Competition where the extra element is used.
  - An element counts as used once the car leaves the pit lane.
  - If a team fits several of the same element at one event, only the last one fitted can be reused later
    without a penalty.
- **B8.2.7 (replacement drivers).** A replacement driver "will be deemed to be the original driver" for PU
  usage.
- **Gearbox.** There is no per-season gearbox limit in 2026. Article B8 has only B8.1 and B8.2. B1.8 refers to a
  "B8.3", but that article does not exist. No 2026 event has published a gearbox document. Out of scope.

## 4. Verified cases (these become the acceptance tests)

1. **Russell, Singapore.**
   - Friday report: ICE 4 / TC 4 / EXH 4 / MGU-K 3 / ES 3 / PU-CE 3 / PU-ANC 5.
   - Decision doc 20: 5th ICE, TC and EXH plus 4th MGU-K, so −40 places.
   - A second decision ("additional changes") added ES and PU-CE.
   - f1db grid penalty: 60. ✔
2. **Lawson, Monza (seat inheritance).**
   - f1db has Lawson at Red Bull and Tsunoda at Racing Bulls for rounds 12–14.
   - The Monza new-elements report (`_1`) shows Lawson had "previously used" 5 ICE. That count is Hadjar's seat.
     Lawson's own seat was still at 4 ICE at Singapore.
   - Decision doc 41 (FP3), −35 places in total:
     - 6th ICE, TC and EXH at 5 places each (B8.2.8b)
     - 4th MGU-K and 7th PU-ANC at 10 places each (B8.2.8a)
   - A separate parc fermé decision (doc 57) sent him to the pit lane.
   - f1db: qualified 14, `PL`, penalty 35. ✔
3. **Alonso, Singapore.** A 6th TC plus parc fermé breaches meant a pit-lane start, and "the grid drop penalty is
   redundant". f1db: `PL`. ✔
4. **US GP (live during research).**
   - Bortoleto: 4th ICE, TC and EXH (all within allowance), plus 4th ES and 4th PU-CE, so −20.
   - Colapinto: 4th PU-CE, so −10.
   - Lindblad: the TD report says his 6th ICE is "not in compliance", but no decision has been published yet. The
     screen therefore needs a **"penalty pending"** state.

## 5. What the screens show

### 5.1 Season overview: `/race-control/power-units`

- One row per seat (22 rows).
- One column per element, showing `used / allowed`, coloured: within allowance → at limit → over.
- Total PU grid places, and the latest event where a new element was fitted.
- The header shows "as of <newest FIA document>". If any document could not be read, it also says
  "N FIA documents couldn't be read".
- Clicking a row opens the driver page.

### 5.2 Driver page: `/race-control/power-units/[driver]`

```
Isack Hadjar · Red Bull Racing (RB Ford)                     as of FIA TD report, Singapore GP
ICE 7/4 (+3)  TC 6/4 (+2)  EXH 6/4 (+2)  MGU-K 4/3 (+1)  ES 4/3 (+1)  PU-CE 4/3 (+1)  PU-ANC 7/6 (+1)
PU grid penalties this season: <places> at <n> Grands Prix · <k> pit-lane starts

By Grand Prix
R13 Italian GP · driven by Liam Lawson — counts against this seat (B8.2.7)
  New: ICE #6 ▲  TC #6 ▲  EXH #6 ▲  MGU-K #4 ▲  PU-ANC #7 ▲          ▲ = beyond allowance
  Stewards (doc 41, FP3): −35 grid places (3 × 5 + 2 × 10)
  Also: pit-lane start for parc fermé changes (doc 57)
  Grid: qualified P14 → started from the pit lane
  Sources: TD report · Decision 41 · Decision 57
```

The counts on the first line are the verified Singapore Friday figures. The totals line is a placeholder.
Lawson's own page shows his Racing Bulls seat, plus an "Also drove" section for the Red Bull seat in rounds 12–14.

### 5.3 Grand Prix Hub: `GridPenalties.tsx`

Add a reason column, filled **only** when a stewards' PU decision matches that driver and event, for example
"PU: 5th ICE, 5th TC … (doc 20)". Otherwise show "—". This keeps the component's rule against inventing an
offence.

### 5.4 Provenance rules (same principles as `docs/HARDCODED_DATA_AUDIT.md`)

- Never infer a reason from the size of a penalty. Reasons come only from stewards' decisions.
- If a TD report says "not in compliance" and no decision exists yet, show "penalty pending", not a number.
- If a document fails to parse, record it and show it as unread. Never skip it silently.
- Show the grid outcome as "pending grid sheet" until f1db publishes the round.

## 6. Architecture

```
fia.com  (index → season → event pages → PDFs)
   │  ingest job: GitHub Action, cron Thu–Mon every 30 min + manual; 10 s crawl delay
   ▼
parse (pypdf) → facts: usage snapshots · element introductions · decisions  (+ source document ref)
   │  single writer
   ▼
Supabase document store: pu_documents (url, sha256, status, extracted text) · pu_facts (by year)
   │  read-only from the web service, 5-min TTL
   ▼
service: seats (← f1db entry lists) · running counts · reconciliation · f1db grid join
   ▼
GET /api/race-control/power-units/{year}               season overview
GET /api/race-control/power-units/{year}/{driver_id}   driver detail (f1db driver id slug)
   ▼
Next.js: /race-control/power-units · /race-control/power-units/[driver] · GridPenalties reason column
```

**Why a GitHub Action, not a loop inside the Render service:**

- Render installs only `requirements.txt` on the free plan (512 MB, sleeps when idle). `pypdf` lives in
  `requirements-ingest.txt`.
- It is untested whether fia.com accepts requests from Render's shared egress IPs. A runner is easy to test and
  retry.
- The web service never writes these documents, so the backfill clobber hazard cannot happen. (That is where
  prod's in-memory copy erases out-of-process writes.)
- There is a precedent: `ingest-rulebook.yml` already runs an ingest with `DATABASE_URL` as a secret.

**Facts stored raw, interpreted at read time.** Fixing the seat mapping or reconciliation needs no re-ingest and
no further requests to the FIA. Storing the extracted text lets the parsers re-run without re-downloading.

### 6.1 Seat model

- A seat is (season, constructor, original driver). Seats are seeded from the season's first "up to now" report
  and the round-1 f1db entry list.
- Each FIA row is resolved two ways: car number → driver using that round's f1db entries, and team name →
  constructor.
- If the row's driver is the seat's known occupant, the row belongs to that seat.
- If the driver is a stand-in:
  1. Assign the team's seat whose occupant is not entered that round.
  2. If that is ambiguous, pick the seat whose counts the row continues (counts never go down).
  3. If it is still ambiguous, flag `seat_ambiguous`, leave the row unattributed and show the flag.
     `driver_availability` replacement records serve as the manual override.

### 6.2 Reconciliation checks

These appear as warnings in the API response and as errors in the job log.

1. Each introduction's "previously used" equals the seat's running count.
2. Each event's snapshot equals the previous snapshot plus the previous event's introductions.
3. The allowance stated in a TD sentence equals the configured allowance (season plus manufacturer bonus). A
   mismatch fails that document.
4. PU decision places are shown next to f1db's applied penalty. This one is informational only, because f1db's
   figure also includes non-PU penalties.

## 7. Files

**Backend, new:**

- `app/data/fia_documents.py`: discovery and polite fetching, using the stdlib `HTMLParser` (no new
  dependency).
- `app/data/pu/` package: `elements.py`, `allowance.py`, `text.py`, `parse_usage_report.py`,
  `parse_new_elements.py`, `parse_decision.py`.
- `app/data/pu_store.py`.
- `app/services/power_units.py`, split into a seats module if it grows past ~400 lines.
- `app/api/routers/power_units.py`.
- `scripts/ingest_pu_documents.py`.
- `.github/workflows/ingest-pu-documents.yml`.
- Tests, with text fixtures taken from the §4 documents.

**Backend, changed:**

- `app/data/store.py`: two document names and their fallback files.
- `app/api/routes.py`: register the router.

**Frontend, new:**

- `app/race-control/power-units/`: `page.tsx`, `PowerUnitsView.tsx`, `powerUnitsModel.ts`, `ElementMeter.tsx`,
  `ElementTimeline.tsx`.
- `app/race-control/power-units/[driver]/`: `page.tsx` and `DriverPowerUnitView.tsx`, following
  `teams/[team]`.

**Frontend, changed:**

- `lib/server/raceControl.ts`: fetchers.
- `RaceControlShell.tsx` and `app/page.tsx`: a "Power Units" nav entry under Decision Tools.
- `grand-prix/GridPenalties.tsx` and `gridModel.ts`: the reason column.

## 8. Phases

Work test-first. Each phase ends green on pytest and the coverage gate, and on
`npm run lint && npm run typecheck && npm run build` with no `eslint-disable`.

1. **Parsers.**
   - Build: the element vocabulary (2025 and 2026 sets); the allowance logic (2026 bonus, 2027 first-year rule);
     the three parsers and the classifier, tested against real-text fixtures covering every quirk in §2.2.
   - Done when: every §4 document parses to the expected facts, and the non-PU parc fermé decision is rejected.
2. **Ingest.**
   - Build: discovery; polite fetching with an injectable delay; idempotency keyed on URL + SHA-256; store
     writes; a CLI with `--year`, `--event` and `--dry-run`.
   - Run the 2026 backfill. Estimate: about 70–120 PDFs, about 15–25 minutes at a 10 s delay.
   - Done when: a re-run changes nothing, and every 2026 document either parses or has its failure explained.
3. **Service and API.**
   - Build: seats, running counts, the per-event timeline, the f1db join, reconciliation, and the two endpoints
     with the `client_error` envelope.
   - Done when: every §4 case comes out right (including Lawson, Hadjar and Tsunoda), with no unexplained
     reconciliation warnings for 2026.
4. **Web.**
   - Build: the overview, the driver page, the nav entry and the GridPenalties reason column.
   - Done when: checked visually on Hadjar (seat inheritance), Russell (two decisions) and Bortoleto or Lindblad
     (pending penalty).
5. **Schedule.**
   - Build: the GitHub Action. The overview shows `as_of` and any unread documents.
   - Done when: a document published during a weekend appears on the site with no deploy.
6. **Optional follow-ups.**
   - An AI Engineer tool, `get_power_unit_usage`.
   - An iOS screen.
   - 2022–2025 history. Those seasons use older element sets, their allowances come from the
     `data/raw/2024|2025` regulations, and gearbox limits existed then.

## 9. Risks

| Risk | Mitigation |
|---|---|
| FIA changes the wording or layout mid-season | Fixtures for each format; fail closed; unread documents are visible on the screen |
| fia.com blocks automated requests | Descriptive user agent, 10 s delay, fetch only new URLs; try from a runner first (Render is untested) |
| Corrected or re-issued documents | Key decisions by (event, car, set of elements); a later document number supersedes |
| A stand-in's seat is ambiguous | Count-continuity check, then a flag, then a manual override via `driver_availability` |
| f1db lags on the grid outcome | A "pending grid sheet" state, as `race_grid.py` already does |
| The FIA season id changes each year | Read it from the FIA index page |

## 10. Open decisions

1. **Stand-ins.** Recommended: seat-based allocation with "driven by" notes, because that is how the FIA counts.
   The alternative is to track strictly per person.
2. **Seasons.** Recommended: 2026 first. The alternative is to add 2022–2025 history now.
3. **Surfaces.** Recommended: web first. The alternative is to add iOS and/or the AI Engineer tool in v1.
4. **Branch.** Start `feature/pu-tracker` off `main`, because `dev` currently holds uncommitted chat work.
