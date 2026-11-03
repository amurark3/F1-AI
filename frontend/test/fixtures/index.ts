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
 * The race-weekend fixtures were captured the same way at 07:50 UTC on 3 Nov,
 * with São Paulo (round 20) the selected weekend:
 *
 * - `overview-shell-2026.json`: `GET /api/race-control/overview/2026/shell`,
 *   kept to `race` (the fields `WeekendHero` reads), `season.total_events` and
 *   `stakes` (as served: Antonelli's title decided, Mercedes able to clinch).
 * - `overview-weather-2026.json`: `…/weather`, without `risk_register`.
 * - `overview-circuit-2026.json`: `…/circuit` (Interlagos), as served.
 * - `overview-predictions-2026.json`: `…/predictions`, each pick kept to the
 *   fields `PodiumPanel` reads.
 * - `overview-strategy-2026.json`: `…/strategy`, re-captured at 08:20 UTC (the
 *   same `pit_model` as at 07:50), kept to the `strategy_context` fields the
 *   baseline strategy panel reads: `primary_call`, `data_source`, `pit_model`
 *   and `stint_windows` (Interlagos 2022 telemetry, high confidence).
 *
 * Other weekends and moments cannot be asked of the endpoints (they serve the
 * selected weekend at the current time), so these were computed by the
 * backend's own functions on real inputs, at the same time:
 *
 * - `stakes-2026-earlier.json`: `stakes.build_championship_stakes` on
 *   `season_events(2026)`, with the table `current_standings.f1db_table` reads
 *   from a copy of f1db v2026.19.0 whose 2026 results and standings stop after
 *   round 0 (pre-season, round 1 selected), 1 (round 2 selected, 10 Mar) and 18
 *   (Mexico City selected, 30 Oct). Each `sources` names the file the table was
 *   read from.
 * - `session-weather-2026.json`: `session_weather.build_session_weather` on the
 *   season's events: Mexico City at 21:00 UTC on 1 Nov (the race live, Open-Meteo's
 *   reading for those hours), Singapore after the weekend, Las Vegas (with the
 *   weather card `overview.weather_blocks` falls back to), Melbourne (round 1,
 *   older than the forecast archive) and no race at all.
 *   `blank_hour` is what `summarise_window` returns for hours Open-Meteo left
 *   blank, as asserted by the backend test
 *   `test_blank_readings_stay_blank_instead_of_reading_as_dry`.
 * - `circuit-records.json`: `circuit_record.circuit_record` for Madring 2026
 *   (round 14, its first Grand Prix, with the schedule's race and circuit
 *   facts), Mexico City 2026 (round 19) and Imola 2020 (round 13), and the
 *   whole `circuit.build_circuit_segment` for Long Beach 1983 (round 2, with
 *   its `season_events(1983)` race: no circuit facts, no lap record, no map).
 *
 * `strategy-panels-2026.json` holds the strategy panels' other states, at
 * 08:20 UTC on 3 Nov, each kept to the fields the panels read:
 *
 * - `sao_paulo_risk_register`: the `risk_register` of `…/weather`, as served
 *   in the same capture (its weather card matches `overview-weather-2026.json`).
 * - `sao_paulo_without_reference`: `strategy_context.build_strategy_context`
 *   for São Paulo with its stored prediction and no telemetry reference, which
 *   is what `strategy_reference_for` returns when the edition cannot be loaded
 *   (a cold FastF1 cache): the heuristic plan, medium confidence.
 * - `spa_without_compounds`: the same function for the Belgian Grand Prix
 *   (round 10, no stored prediction), with the reference
 *   `reference._summarize_circuit_edition` makes from its own 2026 race laps
 *   (the cached FastF1 session) once the `Compound` column is removed: the
 *   backend's `UNKNOWN` compound, which `.title()` sends as "Unknown".
 * - `las_vegas_risk_register`: `risk.build_risk_register` for Las Vegas
 *   (round 21, a street circuit) with the weather card in
 *   `session-weather-2026.json` (`las_vegas_pending.weather`, feed offline) and
 *   the competitor rows from the current constructors' table.
 * - `no_race_risk_register`: the same function with no race: an empty register.
 *
 * Re-capture rather than hand-edit: a fixture is evidence of what the backend
 * sends, never an invented case.
 */
import type { StrategyContext, WeatherCard } from "@/app/race-control/components/CommandCenterPanels";
import type { SeasonDirectory } from "@/app/race-control/profiles/profilesModel";
import type { TeamsResponse } from "@/app/race-control/teams/teamsModel";
import type { PodiumPick } from "@/app/race-control/weekend/PodiumPanel";
import type { HeroRace } from "@/app/race-control/weekend/WeekendHero";
import type {
  ChampionshipStakes,
  CircuitRecord,
  OverviewCircuit,
  RiskCard,
  SessionForecast,
  SessionWeather,
} from "@/app/race-control/weekend/weekendTypes";

import circuitRecords from "./circuit-records.json";
import overviewCircuit2026 from "./overview-circuit-2026.json";
import overviewPredictions2026 from "./overview-predictions-2026.json";
import overviewShell2026 from "./overview-shell-2026.json";
import overviewStrategy2026 from "./overview-strategy-2026.json";
import overviewWeather2026 from "./overview-weather-2026.json";
import directory2026 from "./profiles-directory-2026.json";
import ready from "./ready.json";
import sessionWeather2026 from "./session-weather-2026.json";
import stakes2026Earlier from "./stakes-2026-earlier.json";
import strategyPanels2026 from "./strategy-panels-2026.json";
import teams2026 from "./teams-2026.json";

// JSON imports widen string unions (`role: string`), hence the assertions.
export const TEAMS_2026 = teams2026 as TeamsResponse;
export const DIRECTORY_2026 = directory2026 as SeasonDirectory;
export const READY = ready;

/** São Paulo 2026 (round 20) as the Command Center served it on 3 Nov. */
export const SAO_PAULO_2026 = {
  race: overviewShell2026.race as HeroRace,
  totalRounds: overviewShell2026.season.total_events,
  stakes: overviewShell2026.stakes as ChampionshipStakes,
  weatherCard: overviewWeather2026.weather as WeatherCard,
  weather: overviewWeather2026.session_weather as SessionWeather,
  circuit: overviewCircuit2026 as OverviewCircuit,
  podium: overviewPredictions2026.predicted_podium as PodiumPick[],
  pitModel: overviewStrategy2026.strategy_context.pit_model,
};

/** The stakes on earlier weekends of 2026: before round 1, after round 1, after round 18. */
export const STAKES_2026 = {
  preseason: stakes2026Earlier.preseason as ChampionshipStakes,
  afterRound1: stakes2026Earlier.after_round_1 as ChampionshipStakes,
  afterRound18: stakes2026Earlier.after_round_18 as ChampionshipStakes,
};

/** Session weather for other 2026 weekends and moments. */
export const SESSION_WEATHER_2026 = {
  mexicoCityRaceLive: sessionWeather2026.mexico_city_race_live as SessionWeather,
  singaporeDone: sessionWeather2026.singapore_done as SessionWeather,
  lasVegasPending: sessionWeather2026.las_vegas_pending.session_weather as SessionWeather,
  lasVegasCard: sessionWeather2026.las_vegas_pending.weather as WeatherCard,
  melbourneArchived: sessionWeather2026.melbourne_archived as SessionWeather,
  noSchedule: sessionWeather2026.no_schedule as SessionWeather,
  blankHour: sessionWeather2026.blank_hour as SessionForecast,
};

/** f1db circuit records for other weekends. */
export const CIRCUIT_RECORDS = {
  madring2026: {
    race: circuitRecords.madring_2026.race as HeroRace,
    record: circuitRecords.madring_2026.record as CircuitRecord,
  },
  mexicoCity2026: circuitRecords.mexico_city_2026 as CircuitRecord,
  imola2020: circuitRecords.imola_2020 as CircuitRecord,
  longBeach1983: {
    race: circuitRecords.long_beach_1983.race as HeroRace,
    circuit: circuitRecords.long_beach_1983.circuit as OverviewCircuit,
  },
};

/** The baseline strategy plan for 2026 weekends: as served, and derived by removal. */
export const STRATEGY_2026 = {
  saoPaulo: overviewStrategy2026.strategy_context as StrategyContext,
  saoPauloWithoutReference: strategyPanels2026.sao_paulo_without_reference as StrategyContext,
  spaWithoutCompounds: strategyPanels2026.spa_without_compounds as StrategyContext,
};

/** Risk registers for 2026 weekends. */
export const RISK_REGISTERS_2026 = {
  saoPaulo: strategyPanels2026.sao_paulo_risk_register as RiskCard[],
  lasVegas: strategyPanels2026.las_vegas_risk_register as RiskCard[],
  noRace: strategyPanels2026.no_race_risk_register as RiskCard[],
};
