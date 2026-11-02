# Data sources — audit and plan

_Audited 2026-11-02, against the live APIs and the 2026 Austin (R18) and Mexico City (R19) weekends._

## Why this matters now

F1 is a sport of exact facts. Two failures this week came from where the data was read, not from the code that drew it:

- **The title was decided, and the app didn't know.**
  - After Mexico City (R19), Antonelli has 380 points and Verstappen 261. Only 100 points remain (four races, no sprints), so **Antonelli is the 2026 champion**.
  - The app reads standings from f1db, which still stops at R18. It therefore still says Russell and Hamilton "can catch" him.
  - OpenF1 and Jolpica published R19 tables within hours of the flag, but both had some numbers wrong (see the next section). f1db published at 08:30 UTC, about 10 h after the flag.
- **Retired drivers "ran to the flag".**
  - The Stints tab labels every stint without a matched pit stop "Ran to the flag" (`frontend/app/race-control/grand-prix/StintChart.tsx:47`).
  - In Mexico, Lindblad retired on lap 58 (DNF) and still got the label. So did every mid-race stint, because the stop sheet had no published times yet.
  - OpenF1 `session_result` already says who was classified, retired, didn't start or was disqualified, with laps completed. OpenF1 `pit` has the stationary times.

### Finding: no single API had Mexico right the morning after

The FIA's **Final Race Classification** (document 86, published 01 Nov 19:50 local time) is the authority. The post-race penalties marked `*` dropped Piastri (7th → 13th), Colapinto (8th → 15th) and Gasly (10th → 17th). That moved Lawson to 7th, Bortoleto to 8th, Hadjar to 9th and Hirakawa to 10th.

| Source, morning of 2 Nov                                   | Race order                           | Standings                                                                                |
| ---------------------------------------------------------- | ------------------------------------ | ---------------------------------------------------------------------------------------- |
| FIA document 86                                            | ✅ authoritative                     | —                                                                                        |
| OpenF1 `session_result`                                    | ✅ matches the FIA, including points | —                                                                                        |
| OpenF1 `championship_*`                                    | —                                    | ❌ Red Bull 380; Hadjar's two points for 9th are missing                                 |
| Jolpica                                                    | ❌ the pre-penalty order             | ❌ 7 drivers wrong, e.g. Piastri 150 (should be 144), Lawson 79 (83), Red Bull 380 (382) |
| f1db v2026.19.0 (released 08:30 UTC, ~10 h after the flag) | ✅                                   | ✅ 7/7 match the FIA                                                                     |

**Standings rule.** Never take one feed's table as-is. Use the last f1db round as the base. Add each later round's points from the FIA final classification, or from OpenF1 `session_result` until that document lands. Show the result as **provisional** until f1db confirms it. Cross-check against OpenF1 `championship_*` and Jolpica, and raise an alert when they disagree.

## Source inventory

| Source                                         | What it gives us                                                                                                     | When it lands                                                                                                                   | Auth / limits                                                         | Used today                                             |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------ |
| **f1db** (GitHub release, SQLite)              | Every season since 1950: results, grids, standings, circuits, drivers, constructors                                  | A periodic release; currently round 18                                                                                          | None                                                                  | History, profiles, standings, grid                     |
| **OpenF1** (`api.openf1.org/v1`)               | Sessions, live timing, classification, standings, pit, stints, race control, overtakes, radio, weather (table below) | Minutes after each session; during sessions with a delay                                                                        | Free for historical data; **401 while a session is live** (paid tier) | Telemetry Lab, stints, sessions, circuit key           |
| **Jolpica** (Ergast successor)                 | Results, qualifying, sprint, standings, schedule                                                                     | Hours after the session, but **post-race penalties are applied late** (R19 still showed the pre-penalty order the next morning) | Free; rate-limited                                                    | Schedule, post-quali grid fallback, standings fallback |
| **FIA documents** (fia.com decision documents) | ~80 PDFs a weekend (listed below)                                                                                    | **During the weekend**, minutes after each decision                                                                             | Public; robots.txt crawl delay of 10 s                                | Power-unit elements only                               |
| **MultiViewer**                                | Circuit outline, corner numbers and angles, pit-loss estimates                                                       | Static per season                                                                                                               | Unofficial                                                            | Circuit maps                                           |
| **Open-Meteo**                                 | Hourly forecast per session                                                                                          | Live                                                                                                                            | Free, CC BY 4.0                                                       | Weather                                                |
| **F1 live timing** (livetiming.formula1.com)   | The raw timing feeds FastF1 reads                                                                                    | —                                                                                                                               | **401 since 2026-10-15** (login required)                             | FastF1 only, so cold FastF1 loads now fail             |

### OpenF1 endpoints (probed 2026-11-02 with Austin R18)

| Endpoint                              | Rows at Austin | Key fields                                                                           | Used?  | What it unlocks                                                               |
| ------------------------------------- | -------------- | ------------------------------------------------------------------------------------ | ------ | ----------------------------------------------------------------------------- |
| `meetings`, `sessions`                | 27 / 5         | `meeting_key`, `circuit_key`, dates, GMT offset, `is_cancelled`                      | yes    | Schedule, local times                                                         |
| `drivers`                             | 22             | number, acronym, `full_name` (surname in CAPS), team name and colour, `headshot_url` | partly | Entry list per session, headshots                                             |
| **`session_result`**                  | 22             | position, `number_of_laps`, **`dnf` / `dns` / `dsq`**, gap, duration, points         | **no** | The classification: who finished, who retired and when. Fixes the stints bug. |
| **`championship_drivers` / `_teams`** | 23 / 11        | position and points at start and after the session                                   | **no** | Standings minutes after each race, ahead of f1db                              |
| `laps`                                | 1166           | lap and sector times, speed traps, mini-sector segments, pit-out flag                | yes    | Sessions, Telemetry, race trace                                               |
| `stints`                              | 54             | compound, start and end lap, tyre age at start                                       | yes    | Strategy                                                                      |
| **`pit`**                             | 32             | lap, **`stop_duration`** (stationary), `lane_duration`                               | **no** | Stop times without waiting for Jolpica                                        |
| `race_control`                        | 173            | flags, SC/VSC, **penalties and investigations**, deleted laps, `qualifying_phase`    | partly | A live incident and penalty log                                               |
| **`overtakes`**                       | 220            | overtaker, overtaken, position, time                                                 | **no** | The overtake feed the Race Rewind design assumed didn't exist                 |
| `position` / `intervals`              | 455 / 24,227   | running order; gap and interval over time                                            | partly | Race trace, position chart, battles                                           |
| **`team_radio`**                      | 36             | driver, time, `recording_url` (audio)                                                | **no** | Radio moments in debriefs and the Engineer                                    |
| **`weather`**                         | 159            | air and track temperature, humidity, **rainfall**, wind                              | **no** | Measured track conditions next to the forecast                                |
| `car_data` / `location`               | ~4 Hz          | speed, throttle, brake, gear, RPM; x/y/z                                             | yes    | Telemetry Lab                                                                 |
| `starting_grid`                       | 404            | —                                                                                    | —      | Not served for 2026; the grid comes from FIA documents or Jolpica             |

### FIA documents (one weekend: 2026 Mexico City GP)

| Kind           | Example titles                                                                                                                                    | Becomes                                                                                                                     |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Penalties      | `Infringement - Car 81 - Causing a collision`, `Infringement - Car 11 - Pit Lane Speeding`, `Decision - Car 10 - …`, `Summons - Car 30 - …`       | A **penalty log**: car, offence, session, penalty (time, grid places, points, reprimand, fine), status (summoned → decided) |
| Grid           | `Provisional Starting Grid`, `Final Starting Grid`, `Parts … replaced during Parc Ferme`, `Changes made during Parc Ferme`, `Permission to start` | The grid as it actually started, **with the reason** for every drop (f1db records places, never the offence)                |
| Classification | `Free Practice 1–3 Classification`, `Provisional/Final Qualifying Classification`, `Provisional Race Classification`                              | Results before any API, plus provisional → final changes                                                                    |
| Lap deletions  | `Infringement - Qualifying Deleted Lap Times (- Double Yellow)`                                                                                   | Correct "fastest lap" picks; already a known OpenF1 trap                                                                    |
| Entry list     | `Entry List`, `Revised Entry List`, `Decision - Driver Change TGR Haas F1 Team`                                                                   | Substitutes, such as Hirakawa in the Haas at Mexico                                                                         |
| Power units    | `New PU Elements…`, `PU Elements used per Driver up to now`, `Infringement - Car 77 - PU elements`                                                | Already ingested by the Power Unit tracker                                                                                  |
| Context        | `Timetable`, `Race Director's Competition Notes`, `Pirelli Preview`, `Circuit Map, Pit Lane Drawing`                                              | Session times, track limits, tyre compounds (C1–C5)                                                                         |

## Source of truth, per fact

The rule: **the most authoritative source available at the time wins, and every stored fact keeps its provenance** (source, URL or document number, fetched at, provisional or final).

| Fact                              | During the weekend                                                                                          | After the session                                                                                                                                                                                                                       | Days later / history |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- |
| Schedule, sessions                | OpenF1 `sessions` + FIA timetable                                                                           | —                                                                                                                                                                                                                                       | f1db                 |
| Entry list, substitutes           | FIA entry list and driver-change decisions → OpenF1 `drivers`                                               | —                                                                                                                                                                                                                                       | f1db                 |
| Classification (all sessions)     | FIA provisional classification                                                                              | OpenF1 `session_result` → Jolpica → FIA final                                                                                                                                                                                           | f1db                 |
| Starting grid and penalty reasons | FIA provisional / final starting grid + infringement documents                                              | Jolpica                                                                                                                                                                                                                                 | f1db (places only)   |
| Penalties and investigations      | OpenF1 `race_control` (live) → FIA documents (authoritative)                                                | FIA                                                                                                                                                                                                                                     | stored log           |
| Pit stops and stop times          | OpenF1 `pit`                                                                                                | Jolpica pit stops                                                                                                                                                                                                                       | stored               |
| Stints and compounds              | OpenF1 `stints` + FIA Pirelli preview (C-numbers)                                                           | —                                                                                                                                                                                                                                       | stored               |
| Standings                         | —                                                                                                           | **Computed:** the last f1db round + FIA final classification points (OpenF1 `session_result` until the document lands), marked provisional. Cross-checked against OpenF1 `championship_*` and Jolpica, which are **not trusted as-is**. | f1db                 |
| Overtakes, positions, intervals   | OpenF1                                                                                                      | —                                                                                                                                                                                                                                       | stored               |
| Weather                           | Open-Meteo forecast + OpenF1 measured                                                                       | —                                                                                                                                                                                                                                       | stored               |
| Telemetry                         | OpenF1 `car_data` / `location` (not live)                                                                   | —                                                                                                                                                                                                                                       | `analysis_cache`     |
| Names and teams                   | f1db `driver.name` / constructor id, resolved from any feed's code, number or name (`app/data/identity.py`) | —                                                                                                                                                                                                                                       | —                    |

## What to store

Today most feeds are read on demand and cached per process. That's why a restart or a cold feed changes what the site says. The plan is to **ingest once and serve from Postgres**, keyed by `(year, round, session)`:

- `sessions`, `entries`: the weekend skeleton, including substitutes.
- `classifications`: per session and driver. Position, status (`finished` / `dnf` / `dns` / `dsq` / `not classified`), laps completed, gap, points. Each row carries a provisional or final flag and its source.
- `grid`: qualifying position, grid slot, places dropped, **reason**, and `pit_lane_start`.
- `penalties`: car, driver id, session, offence, penalty kind and value, status, decision document URL.
- `pit_stops`, `stints`, `overtakes`, `race_control_messages`, `weather_observations`, `team_radio` (URL only).
- `standings_snapshots`: after each session, from OpenF1 `championship_*`.

**Ingest cadence**

- **Weekend live window (Thursday to Sunday):**
  - the FIA document list every 5 minutes, honouring the 10 s crawl delay (only new documents are fetched);
  - OpenF1 endpoints for a session as soon as it ends, and again an hour later.
- **Monday:** Jolpica reconciliation.
- **f1db release:** backfill history and mark f1db as the long-term source.
- The existing GitHub Actions ingest (`scripts/*`, `--require-database`) is the pattern to follow.

## Accuracy rules: edge cases every screen must handle

1. **Finished vs retired vs not started vs disqualified.** Never infer from lap counts or stints. Read `session_result` or the FIA classification. A retired driver's last stint ends **"Retired · lap N"**, never "ran to the flag".
2. **Classified but not running.** A driver who stopped after 90% distance is classified; show both facts.
3. **Pit-lane starts and grid penalties.** The grid slot is not the qualifying position. Show places dropped and the FIA reason. A pit-lane start is not "P22".
4. **Red flags.** Tyre changes under a suspension are not pit stops; this is already handled for Monza 2026. A shortened race may award reduced points.
5. **Stops with no published time.** Write "time not published yet", not "no stop".
6. **Deleted laps.** Apply FIA lap deletions before naming any "fastest" lap.
7. **Provisional vs final.** Results and grids change after decisions, so show which one is on screen.
8. **Rosters are seats, not people.** A weekend has 22 cars and at most 2 per team. Read the entry list from OpenF1 `drivers` / the FIA entry list, never the season's championship table. The championship table is the reason the R20 Brazil prediction showed 23 drivers.
9. **Substitutes and team names.** Driver changes (Hirakawa for Haas at Mexico) and team aliases ("RB F1 Team", "Visa Cash App RB" → Racing Bulls) resolve through `identity.py`.
10. **Stale sources.** Every number shows how fresh it is. Never treat an old snapshot as current: the "stakes" panel must count from the latest standings, not f1db's last round.
11. **Live lockout.** OpenF1 returns 401 during live sessions. Say "live data unavailable", never "no data".
