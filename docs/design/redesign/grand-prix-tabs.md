# Grand Prix hub: what each tab answers (P4.3a)

_Design spec, 2026-11-14. No app code. **The user signs off before P4.3b starts.**_

Every tab answers one question. Every column on it serves that question or goes. All examples use real 2026 Mexico City (R19) data from the FIA documents named in `docs/DATA_SOURCES.md`, f1db v2026.19.0+ (which mirrors the FIA final classification) and the fixtures in `backend/tests/fixtures/mexico_2026_r19/`.

Mockups: `grand-prix.html` (Weekend), `gp-sessions.html`, `gp-grid.html`, `gp-results.html` (new), `gp-stints.html`, `gp-predictions.html` (Order view), `gp-review.html` (new, the Review view).

## Tab order

**Weekend · Sessions · Grid · Results · Stints · Predictions**

- The first four follow the weekend: what's on, how practice and qualifying went, where the cars started, how the race was classified.
- Stints sits after Results because its rows are in classification order and it explains how that order was reached.
- Predictions is last because it spans the weekend: a call before qualifying, a call after, and a Review that reads Results.

Every round opens on **Weekend** when the URL names none, whatever stage its weekend has reached, and picking another round starts over on Weekend (user, 2026-11-18). The calendar-driven default this replaced (Sessions mid-weekend, Grid after qualifying, Results after the race) changed tabs on some round switches but not others: only until a tab was clicked, which then stuck. A link can still name a tab (`?tab=results`).

The hero and the facts strip sit above the tabs on **every** tab, as `grand-prix.html` draws them, so switching tabs never moves the page above them (user, 2026-11-18: a Weekend-only hero looked out of place). The one-line race header shows only while no round is selected. The other tab mockups still draw that one-line header; a comment in each marks it as replaced.

The season strip marks the selected round by height, never by red (red reads as Ferrari): a won round keeps its winning team's colour, any other is white (user, 2026-11-18).

`GrandPrixTab` and `HUB_TABS` gain `results` (`?tab=results`), placed fourth.

## Shared rules

**Names.** Full name in heroes and grid cards; surname + code in tables; code on chart axes. A substitute carries a `Sub` tag naming the seat (Hirakawa in Ocon's Haas). Team identity is the colour bar plus the team name where there's room; colour is never the only carrier.

**One vocabulary for special states.** Every tab uses the same words, so a state reads the same everywhere.

| State               | Reads                            | Where the fact comes from                         | Notes                                                                                                                                          |
| ------------------- | -------------------------------- | ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Finished            | `7`                              | FIA classification                                | The position number. No "P" prefix in a Pos column.                                                                                            |
| Lapped              | `+1 lap`                         | FIA classification                                | In the time/gap cell.                                                                                                                          |
| Retired             | `DNF` · reason · laps completed  | FIA classification + f1db `race_reason_retired`   | Never the classified place (18–22 in Mexico). Gains no places. Red text (`--red-text`).                                                        |
| Not classified      | `NC` · laps completed            | FIA classification                                | Running at the end but under 90% distance. **Not** a retirement word: Mexico had none, and the old Stints mockup misused NC for its five DNFs. |
| Did not start       | `DNS` · reason                   | FIA classification                                |                                                                                                                                                |
| Disqualified        | `DSQ` · offence · FIA doc        | FIA decision                                      | Lawson, Mexico qualifying (doc 57).                                                                                                            |
| Classified, stopped | position + `Stopped · lap n`     | FIA classification                                | Accuracy rule 2: both facts. None in Mexico.                                                                                                   |
| Pit-lane start      | `Pit lane` · reason · FIA doc    | FIA final starting grid + decision                | Never `P22`. Lawson, Mexico (docs 57, 65).                                                                                                     |
| Time penalty        | `incl. 10 s` · on-the-road place | FIA final classification (`*`) + decision         | Only penalties added to the race time. Penalties served in the pits are the Debrief's story.                                                   |
| Grid penalty        | `−1 place` · reason · FIA doc    | FIA decision; f1db has the places only            |                                                                                                                                                |
| No time set         | `No Q3 time`                     | The part's timed entries (who ran in it)          | Only for a car that ran in that part and set no time. None in Mexico.                                                                          |
| Promoted by a DSQ   | `Up 1 · LAW DSQ`                 | Qualifying classification + the FIA decision      | Hülkenberg (out in Q2, classified P10) and Albon (out in Q1, P16) after Lawson's disqualification (doc 57).                                    |
| FP1 stand-in        | `FP1 run` · whose car            | OpenF1 `drivers` for the session / FIA entry list | Mexico FP1 had nine (Herta, Crawford, Iwasa, Browning, Minì, Fornaroli, Vesti, Tsolov, Slater).                                                |
| Provisional / Final | tag beside the section title     | Which source is on screen                         | Final = the FIA final classification (or f1db mirroring it). Provisional = anything earlier. Blue (`--blue`, info) for provisional.            |

**Provenance line.** Every section ends with a `.note` naming its sources and whether the data is final.

**Phones (390 px).** No page scrolls sideways. Each table names its column priority below; lower-priority columns hide rather than squeeze. Tabs scroll inside their own strip.

## Weekend

**Question:** what is this weekend, when is each session, and what is at stake?

**Data and authority:** schedule from OpenF1 `sessions` + the FIA timetable; circuit layout from MultiViewer; circuit facts and past winners from f1db; stakes computed from the last f1db round plus later rounds' FIA classifications, marked provisional until f1db confirms (Standings rule).

| Block           | Column / fact                             | Meaning                                   | Unit        | Special states                                                        |
| --------------- | ----------------------------------------- | ----------------------------------------- | ----------- | --------------------------------------------------------------------- |
| Hero            | Next session countdown                    | Time to the next session start            | d / h / min | Live: "Live now"; all done: replaced by the winner and a Results link |
| Facts strip     | Lap                                       | Lap length                                | km          |                                                                       |
|                 | Laps                                      | Scheduled race laps                       | laps        | A shortened race shows the laps run in Results, not here              |
|                 | Distance                                  | Scheduled race distance                   | km          |                                                                       |
|                 | Corners                                   | Corner count, direction                   | count       |                                                                       |
| Schedule        | Session, day, time                        | Each session's start in the viewer's zone | local time  | Done / next / live / cancelled                                        |
| Circuit history | Year, winner, team                        | The last four editions at this venue      | —           | A venue new to the calendar says so                                   |
| Stakes          | Driver/team, points, most still reachable | The live title or position fights         | points      | Clinched (banner), provisional standings tag                          |

- **Removed:** "Last winner here" from the facts strip. Circuit history lists the same winner one panel below.
- **Added:** once the race is classified, the hero's countdown slot shows the winner and "Final classification →" (Results). The Weekend tab doesn't print results itself.

## Sessions

**Question:** how did each practice and qualifying session classify, and by how much?

**Data and authority:** FIA session classifications (provisional, then final) → OpenF1 `session_result` (qualifying `duration` and `gap_to_leader` per part) → f1db. Lap deletions are applied before any "fastest" (accuracy rule 6). DSQ labels come from f1db/Jolpica and the FIA decision, because OpenF1's `dsq` is false for Lawson.

**Sessions on the strip:** practice and qualifying only (FP1–FP3, plus sprint qualifying on a sprint weekend). The race and the sprint move to Results; the sprint grid moves to Grid.

Qualifying columns:

| Column       | Meaning                                                                            | Unit     | Special states                                                                                                    |
| ------------ | ---------------------------------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------- |
| Pos          | Final qualifying position                                                          | —        | `DSQ` rows sit below a red cut line, with offence and FIA doc                                                     |
| Driver       | Surname + code, team bar                                                           | —        | `Up 1 · LAW DSQ` when a disqualification moved them up; `No Q3 time` only for a car that ran in Q3 without a time |
| Q1 / Q2 / Q3 | Best valid lap in each part                                                        | m:ss.sss | `—` = didn't run in that part. Purple = fastest in that part (sector-best meaning)                                |
| Gap          | Gap to the fastest lap **of the part the driver was classified in** (bar + number) | s        | Pole reads `POLE`; no time in that part: `—`; DSQ: `—`                                                            |
| Cut rows     | "Knocked out in Q2" / "Knocked out in Q1"                                          | —        | Grouped by the part each car **ran in on the road**, never by classified position                                 |

Practice columns: Pos · Driver · Best lap (m:ss.sss) · Gap to the fastest (s) · Laps run (count). Laps stay in practice: how much each car ran is part of the answer there. FP1 stand-ins carry `FP1 run · <regular driver>'s car`.

- **Removed:** Team column (today's app); the colour bar and the hover carry it. "Starts from pit lane" on Lawson's row: that's the Grid's answer.
- **Changed:** Gap was "gap to pole from each driver's best lap", which compares laps from different parts. It disagreed with the official figure: Norris read +0.214 (his Q2 lap) against the classification's +0.310 (his Q3 lap). It is now the gap inside the driver's own part, as OpenF1 `gap_to_leader` and f1db publish it.
- **Fixed: who reached which part.** Q3 had exactly ten timed cars (P1–P9 and Lawson) and Q2 sixteen (P1–P15 and Lawson). Hülkenberg was knocked out in Q2 and Albon in Q1; each moved up one when Lawson was disqualified after the session. The old mockup's `No Q3 time` on Hülkenberg was wrong, and so is PLAN P4.5's "Hülkenberg reached Q3 / Albon reached Q2" and its 10 / 6 / 6 groups: the groups are 9 / 6 / 6 plus the DSQ. The part reached comes from each part's timed entries (with the disqualified car counted), not from the classified position.
- **Fixed:** the stewards card said "two decisions changed this order", but only Lawson's disqualification changed qualifying; Verstappen's drop changed the grid.
- **Phone priority:** Pos, Driver, the driver's time in their last part (one combined cell), Gap number. Q1/Q2/Q3 columns and the bar hide.

## Grid

**Question:** where did each car start, and why isn't it where it qualified?

**Data and authority:** FIA final starting grid (Mexico doc 67) for the order; FIA decisions for every reason (Mexico 17, 33, 57, 65); Jolpica after the session; f1db for history (places dropped, never the offence). On a sprint weekend a `Grand Prix · Sprint` switch shows the sprint's grid sheet.

| Column (per car card) | Meaning                                                     | Unit   | Special states                                                      |
| --------------------- | ----------------------------------------------------------- | ------ | ------------------------------------------------------------------- |
| Slot                  | Grid slot                                                   | —      | Pit-lane starters sit in the pit-lane box, never in a numbered slot |
| Driver                | Full name + code, team bar                                  | —      | Sub tag                                                             |
| Qualified             | Qualifying position, **only when it differs from the slot** | —      | `DSQ` for a disqualified qualifier                                  |
| Penalty               | Places, offence, FIA doc                                    | places | No effect: "already at the back" (Bottas, −50 from P21 of 21)       |
| Promoted              | Places gained from someone else's drop                      | places | `--gain` green                                                      |

- **Removed:** "Qualified Pn" on cars that started where they qualified (18 of 22 in Mexico said the same number twice). The "From the grid to the flag" card: who won from where is Results and the Debrief.
- **Added:** a Results link in its place. Bottas's −50 now says it cost nothing.
- **Phone priority:** both grid columns stay; names wrap.

## Results (new)

**Question:** what is the official classification of the race (and the sprint), and is it final?

**Data and authority:** the FIA final race classification (Mexico doc 86), which f1db mirrors until D2.3 ingests the documents. Before it lands: OpenF1 `session_result` (it matched the FIA in Mexico), marked **provisional**. Jolpica is never the authority here: it showed the pre-penalty order the next morning. Retirement reasons from f1db `race_reason_retired` until D2. Fastest lap from f1db (the FIA fastest-laps document).

**Sprint:** on a sprint weekend a `Sprint · Grand Prix` switch sits above the table; the sprint uses the same columns. Mexico had no sprint, so no switch.

| Column     | Meaning                                      | Unit             | Special states                                                                                                             |
| ---------- | -------------------------------------------- | ---------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Pos        | Classified position                          | —                | `DNF`, `NC`, `DNS`, `DSQ` in place of a number; winner's numeral in gold                                                   |
| Driver     | Surname + code, team bar                     | —                | `Sub` (seat named), `Fastest lap` (purple)                                                                                 |
| Team       | Constructor                                  | —                |                                                                                                                            |
| Time / gap | Winner: race time; others: gap to the winner | h:mm:ss.sss / +s | `+1 lap`; time penalties: `incl. +10 s · P7 on the road`; DNF/NC/DNS: reason and laps completed in red; DSQ: offence + doc |
| Pts        | Points scored                                | points           | `0` muted for no score (a fact, not a missing value)                                                                       |

Row order: classified cars by position, then NC, then DNF by laps completed (FIA order), then DNS, then DSQ. Non-finishers sit below a labelled cut row ("Did not finish").

Side panels: **Changed after the flag** (each post-race penalty: on-the-road place → classified place, penalty, offence or document; who moved up); **Fastest lap**; a link to the Debrief.

- **Not columns, on purpose:** Grid and places gained (Grid tab and the Debrief's grid→finish chart own them); Laps (every finisher ran 71; lapped cars read `+1 lap`, non-finishers carry their laps in the reason cell); Interval and average speed (the gap answers "how far behind"); car number (the code identifies the car).
- **Phone priority:** Pos, Driver, Time/gap, Pts. Team hides.

## Stints

**Question:** what tyres did each car run, and when did it stop?

**Data and authority:** OpenF1 `stints` + the Pirelli preview for C-numbers; stops and pit-lane times from OpenF1 `pit`, then the Jolpica pit sheet with red-flag entries removed; the finish state from the classification (P0.1 logic, unchanged).

| Column | Meaning                                     | Unit  | Special states                                                                                                                  |
| ------ | ------------------------------------------- | ----- | ------------------------------------------------------------------------------------------------------------------------------- |
| Pos    | Classified position, so the row order reads | —     | `DNF` for a retirement (was `NC`), `NC`, `DNS`, `DSQ`                                                                           |
| Driver | Surname + code, team bar                    | —     |                                                                                                                                 |
| Stints | One bar per stint, compound and laps        | laps  | Used set (hatched), compound not recorded, red-flag change (not a stop), SC/VSC bands, × retired with the reason in its tooltip |
| Stops  | Pit stops made                              | count | `DNF · L58` tag; "time not published yet" in the tooltip when a stop has no time                                                |

- **Fixed:** the five Mexico retirements read `DNF`, not `NC`, and each tooltip carries the reason (Lindblad: collision).
- **Open for P4.3b:** Lawson's lap-11 pit-lane pass appears in OpenF1 `pit` (22.8 s) and the Jolpica sheet (22.855 s), but OpenF1 `stints` shows no tyre change and f1db counts two stops. P4.3b labels it from a source (e.g. a drive-through in race control) or leaves it out; it never guesses.
- **Phone priority:** Pos, code, the stint bars. The Stops column hides; the Pos column still says DNF.

## Predictions

**Question:** where does the model expect each car to finish, and once the race is run, how good was that call?

**Data and authority:** the stored prediction snapshots (pre- and post-qualifying), the risk model, and **Results** for scoring. Nothing in this tab prints race results of its own.

Order view (`gp-predictions.html`):

| Column    | Meaning                                                                                                  | Unit        | Special states                                                                   |
| --------- | -------------------------------------------------------------------------------------------------------- | ----------- | -------------------------------------------------------------------------------- |
| P         | Called finishing position                                                                                | —           |                                                                                  |
| Driver    | Full name + code, team bar                                                                               | —           | `Seat TBC` until the entry list publishes                                        |
| Agreement | How closely the model's inputs agree on this driver (`_compute_confidence`: spread of the input signals) | score, no % | Not a probability; see Decisions                                                 |
| vs grid   | Called finish against the starting grid (post-qualifying only)                                           | places      | Hidden before qualifying (no grid to compare). Pit-lane starter: "from pit lane" |

- **Removed from the order table** (today's `FullGridTable`): Team (bar), Pts (a lookup of the points table, adds nothing), Win est. and Podium est. (the Podium view answers "who wins"), Crash % and DNF % (the Risk view owns them).
- **Changed:** "Confidence 60–75%" read like a probability. It is a signal-agreement score, so it loses the % sign and says what it is.

Review view (`gp-review.html`): **it scores the call against Results and prints no results table.**

| Block                | Meaning                                                                                        | Unit           | Special states                                                                                         |
| -------------------- | ---------------------------------------------------------------------------------------------- | -------------- | ------------------------------------------------------------------------------------------------------ |
| Score strip          | Winner right, podium overlap, top-ten overlap, average miss over classified cars               | count / places | "Scored against the provisional result" until Results is final; re-scored when it changes              |
| Call vs result chart | One row per car in **called** order: a ring at the call, a dot at the result, the gap between  | places         | `vs call`: `+n` finished ahead of the call, `−n` behind, `0` exact                                     |
| DNF rows             | The call, `DNF` · reason, and whether the risk model flagged it (≥ 16%, the scoring threshold) | %              | **No place delta.** Excluded from exact / within-3 / average miss; scored only as a retirement call    |
| Retirement calls     | Retirements the risk model flagged / all retirements; cars flagged in total                    | count          | Crash vs mechanical read from the Results reason (collision, accident = incident; engine = mechanical) |

- **What "vs call" shows for a DNF:** `DNF` and the reason, never a number. Comparing a call with a retirement's classified place (18–22) would score the car's retirement order, which the model never predicted.
- **Removed:** the "Predicted vs actual — every driver" table with its Actual and Outcome columns. It was a second results table, and it was wrong (below).
- Colour: `vs call` values are neutral ink. Green (`--gain`) stays for positions gained in a race; beating a call isn't one.

## Results and the Debrief

| Results (Grand Prix hub)                                                | Debrief (`debrief.html`, P6.1)                                                           |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| The official classification: who, where, how far behind, points         | The story: headline, podium, lap leaders, race trace with SC/VSC/red flag                |
| Is it final, and which document says so                                 | Grid → finish movement, biggest climbs                                                   |
| Post-race penalties that changed the classification (road → classified) | The full penalty timeline, in-race and post-race, including penalties served in the pits |
| Retirement reason and laps completed                                    | When and how each retirement happened in the race                                        |
| Fastest lap (one fact)                                                  | Overtakes, battles, radio moments (P6.2)                                                 |

Each links to the other. The Debrief never prints the full classification table; Results never draws the race.

## Defects found while designing (real R19 data)

1. **The stored Review scored against Jolpica's pre-penalty order.** The R19 `prediction_history` entry stores `actual_positions` PIA 7, COL 8, LAW 9, GAS 10 and the retirements at 18–22. The FIA order is LAW 7, BOR 8, HAD 9, HIR 10, PIA 13, COL 15, GAS 17, and the retirements have no place. The Review reads Results instead, and re-scores when Results moves from provisional to final.
2. **Crash calls can't score.** The same entry stores `crash: false` for all five retirements, but f1db gives Lindblad "Collision", Bearman "Collision damage", Bottas "Accident". The reason has to come from the classification.
3. **Qualifying gap mixed parts** (Sessions, above): Norris +0.214 vs the official +0.310.
4. **Who reached which qualifying part** (Sessions, above): Hülkenberg and Albon were knocked out on the road and promoted by Lawson's DSQ. This also corrects PLAN P4.5's accept list (groups 9 / 6 / 6 + DSQ, not 10 / 6 / 6).
5. **Stints used NC for retirements**; the Sessions stewards card miscounted the decisions that changed the order.

## Decisions for the user

1. **Tab order:** Weekend · Sessions · Grid · Results · Stints · Predictions, and a finished race opens on Results (today it opens on Predictions › Review). Superseded 2026-11-18: every round opens on Weekend.
2. **Results has no Grid or places-gained column.** The Grid tab and the Debrief's grid→finish chart own movement. The alternative is a "Started" column on Results.
3. **Results has no Laps column.** Finishers read `+1 lap` when lapped, and non-finishers carry laps in the reason cell (`Collision · 58 laps`).
4. **Qualifying gap is measured within the driver's own part** (official figure), not from each driver's best lap across parts.
5. **A DNF in the Review reads `DNF` · reason, with no place delta**, and is scored only as a retirement call (risk ≥ 16% = flagged). It is excluded from exact, within-3 and average miss.
6. **"Confidence 60–75%" becomes "Agreement 60–75" without the % sign**, because it's the spread of the model's inputs, not a probability. The alternative is to drop it from the order view.
7. **The Order view drops Pts, Win est., Podium est., DNF % and Crash %** (Podium and Risk views own them); "vs grid" shows only after qualifying.
8. **A pit-lane start counts from the back of the grid** when places gained are computed (f1db does: Lawson +15 from the pit lane), and always reads "from the pit lane", never "from P22".
9. **The sprint lives in Results (classification) and Grid (its grid)**; Sessions keeps practice, sprint qualifying and qualifying.
