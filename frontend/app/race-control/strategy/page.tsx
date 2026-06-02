"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { ChevronDown, Gauge, PlayCircle, SlidersHorizontal, Target, Timer, UserRound } from "lucide-react";
import { API_BASE } from "@/app/constants/api";
import { fetcher } from "@/app/utils/fetcher";
import { InlineNotice, MetricCard, MetricRow, Panel, SectionHeader, SectionLoader, StatusPill, WorkspaceSplit, rcFont } from "../components/RaceControlPrimitives";
import { TyreDegradationChart } from "../components/Charts";

interface DriverOption {
  code: string;
  name: string;
  team: string;
  position: number;
  points: number;
}

interface DriversResponse {
  drivers: DriverOption[];
  error?: string | null;
}

interface SimulationRequest {
  year: number;
  race: string;
  team: string;
  driver: string;
  current_lap: number;
  starting_position: number;
  tyre_compound: string;
  tyre_age: number;
  pit_lap: number;
  traffic_risk: number;
  safety_car_probability: number;
  weather_risk: number;
}

interface SimulationResult {
  recommendation: { plan: string; pit_window: string; rationale: string; confidence?: string; branch_delta?: number };
  data_quality?: {
    grade: string;
    observed_sources: number;
    total_sources: number;
    scenario_inputs: string[];
    note: string;
  };
  data_sources?: Array<{ label: string; status: string; value: string; source?: string | null }>;
  reference?: {
    status?: string | null;
    summary?: string | null;
    race?: { name?: string | null; round?: number | null; location?: string | null; status?: string | null; total_laps?: number | null; circuit?: string | null };
  };
  stint?: {
    current_lap: number;
    tyre_age_now: number;
    tyre_age_at_stop: number;
    compound_life: number;
    compound_reference_source?: string;
    compound_reference_status?: string;
    life_used_pct: number;
    laps_to_stop: number;
  };
  plans: Array<{ name: string; score: number; expected_finish: string; pit_window: string; risk: string; notes: string[] }>;
  battle_cards: Array<{ label: string; value: string; call?: string | null }>;
  model_inputs?: Array<{ label: string; value: string; impact: string; source: string; tone: "good" | "warning" | "critical" }>;
  decision_matrix?: Array<{ gate: string; status: string; detail: string }>;
}

const year = new Date().getFullYear();

const TYRE_LIFE: Record<string, number> = {
  SOFT: 18,
  MEDIUM: 29,
  HARD: 42,
  INTERMEDIATE: 24,
  WET: 20,
};
const DEFAULT_GRID_SIZE = 22;

const STRATEGY_PRESETS = [
  {
    key: "balanced",
    label: "Balanced",
    detail: "Normal dry-race assumptions.",
    values: { traffic_risk: 45, safety_car_probability: 35, weather_risk: 20 },
  },
  {
    key: "attack",
    label: "Clean-air attack",
    detail: "Lower traffic risk, undercut friendly.",
    values: { traffic_risk: 25, safety_car_probability: 25, weather_risk: 10 },
  },
  {
    key: "safety-car",
    label: "Safety-car hedge",
    detail: "Keep a flexible stop branch open.",
    values: { traffic_risk: 45, safety_car_probability: 60, weather_risk: 15 },
  },
  {
    key: "rain-threat",
    label: "Rain threat",
    detail: "Higher crossover and track-state risk.",
    values: { traffic_risk: 50, safety_car_probability: 45, weather_risk: 55 },
  },
] as const;

type StrategyPreset = (typeof STRATEGY_PRESETS)[number];

const fieldClass = "h-12 w-full rounded-lg border border-white/12 bg-[#151817] px-3 text-base font-semibold text-white outline-none transition-colors focus:border-[#00FF78]/70 focus:ring-2 focus:ring-[#00FF78]/15 disabled:text-neutral-500";

async function simulate(url: string, { arg }: { arg: SimulationRequest }) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(arg),
  });
  if (!res.ok) throw new Error(`Simulation failed: ${res.status}`);
  return res.json() as Promise<SimulationResult>;
}

function buildDriverChoices(team: string, drivers: DriverOption[]) {
  const teamDrivers = drivers.filter((driver) => driver.team === team);
  return teamDrivers.map((driver) => ({
    value: driver.name,
    label: `${driver.name} (${driver.code})`,
    meta: `WDC P${driver.position} · ${driver.points} pts`,
  }));
}

export default function StrategySimulatorPage() {
  const [lastRunAt, setLastRunAt] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [activePreset, setActivePreset] = useState<string>("balanced");
  const [form, setForm] = useState<SimulationRequest>({
    year,
    race: "Next Grand Prix",
    team: "McLaren",
    driver: "Lando Norris",
    current_lap: 14,
    starting_position: 5,
    tyre_compound: "MEDIUM",
    tyre_age: 12,
    pit_lap: 22,
    traffic_risk: 45,
    safety_car_probability: 35,
    weather_risk: 20,
  });

  const { data: driversData, error: driversError, isLoading: driversLoading, mutate: reloadDrivers } = useSWR<DriversResponse>(
    `${API_BASE}/api/race-control/drivers/${year}`,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 180000 }
  );

  const drivers = useMemo(() => driversData?.drivers ?? [], [driversData?.drivers]);
  const teamOptions = useMemo(() => {
    const realTeams = Array.from(new Set(drivers.map((driver) => driver.team).filter(Boolean)));
    return realTeams;
  }, [drivers]);
  const selectedTeamIsValid = teamOptions.includes(form.team);
  const effectiveTeam = selectedTeamIsValid ? form.team : teamOptions[0] ?? "";
  const driverChoices = useMemo(() => buildDriverChoices(effectiveTeam, drivers), [drivers, effectiveTeam]);
  const selectedDriverIsValid = driverChoices.some((driver) => driver.value === form.driver);
  const effectiveDriver = selectedDriverIsValid ? form.driver : driverChoices[0]?.value ?? "";
  const effectivePitLap = form.pit_lap <= form.current_lap ? Math.min(70, form.current_lap + 1) : form.pit_lap;
  const gridSize = Math.max(DEFAULT_GRID_SIZE, drivers.length);

  const { trigger, data, error, isMutating } = useSWRMutation(
    `${API_BASE}/api/race-control/strategy/simulate`,
    simulate
  );

  const compoundLife = TYRE_LIFE[form.tyre_compound] ?? TYRE_LIFE.MEDIUM;
  const lapsToStop = Math.max(0, effectivePitLap - form.current_lap);
  const tyreAgeAtStop = form.tyre_age + lapsToStop;
  const tyreLifeUsed = Math.round((tyreAgeAtStop / compoundLife) * 100);
  const driverMeta = driverChoices.find((driver) => driver.value === effectiveDriver)?.meta;
  const canRun = Boolean(effectiveTeam && effectiveDriver && !isMutating);
  const runStatus = isMutating
    ? "Simulation is running. Results will update in the panels below."
    : runError
      ? runError
      : lastRunAt
        ? `Last run completed at ${lastRunAt}.`
        : effectiveDriver
          ? "Ready to run. Set the stint state, then run the branch comparison."
          : "Load a standings-backed team and driver before running the model.";

  const update = (key: keyof SimulationRequest, value: string | number) => {
    if (key === "traffic_risk" || key === "safety_car_probability" || key === "weather_risk") {
      setActivePreset("custom");
    }
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const applyPreset = (preset: StrategyPreset) => {
    setActivePreset(preset.key);
    setForm((prev) => ({ ...prev, ...preset.values }));
  };

  const updateTeam = (team: string) => {
    const nextDriver = buildDriverChoices(team, drivers)[0]?.value ?? "";
    setForm((prev) => ({ ...prev, team, driver: nextDriver }));
  };

  const updateCurrentLap = (currentLap: number) => {
    setForm((prev) => ({
      ...prev,
      current_lap: currentLap,
      pit_lap: prev.pit_lap <= currentLap ? Math.min(70, currentLap + 1) : prev.pit_lap,
    }));
  };

  const run = async () => {
    if (!effectiveTeam || !effectiveDriver || isMutating) return;

    setRunError(null);
    try {
      await trigger({
        ...form,
        team: effectiveTeam,
        driver: effectiveDriver,
        pit_lap: effectivePitLap,
      });
      setLastRunAt(new Intl.DateTimeFormat("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }).format(new Date()));
    } catch (err) {
      setRunError(err instanceof Error ? err.message : "Simulation request failed.");
    }
  };

  return (
    <div>
      <SectionHeader
        eyebrow="Strategy Simulator"
        title="Pit Window Lab"
        description="Pick the car, set the current stint state, then run the pit call. Advanced race risks are handled with presets unless you need to tune them."
      />

      <WorkspaceSplit>
        <Panel className="h-fit p-5">
          <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#00FF78]" style={rcFont}>Pit call setup</p>
              <h2 className="mt-1 text-2xl font-semibold text-white" style={rcFont}>Set the car, then the stint</h2>
              <p className="mt-2 text-sm leading-relaxed text-neutral-400">
                The basic workflow only needs the car, where it is running, tyre age, and the lap you want to test.
              </p>
            </div>
            <StatusPill color="#3671C6">Stint model</StatusPill>
          </div>

          <div className="space-y-6">
            <section>
              <StepHeading
                step="1"
                title="Choose the car on track"
                detail="Use real standings-backed drivers and the car's current race position."
              />
              <div className="mt-4 flex flex-col gap-4 md:flex-row md:flex-wrap [&>*]:min-w-[240px] [&>*]:flex-1">
                <label className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-300">Team</span>
                  <select value={effectiveTeam} onChange={(e) => updateTeam(e.target.value)} disabled={!teamOptions.length} className={fieldClass}>
                    {!teamOptions.length && <option value="">Standings feed required</option>}
                    {teamOptions.map((team) => <option key={team}>{team}</option>)}
                  </select>
                </label>
                <label className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-300">Driver</span>
                  <select value={effectiveDriver} onChange={(e) => update("driver", e.target.value)} disabled={!driverChoices.length} className={fieldClass}>
                    {!driverChoices.length && <option value="">Select a standings-backed team</option>}
                    {driverChoices.map((driver) => <option key={driver.value} value={driver.value}>{driver.label}</option>)}
                  </select>
                  {driverMeta && <p className="text-sm text-neutral-500">{driverMeta}</p>}
                </label>
                <label className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-300">Track position now</span>
                  <input
                    type="number"
                    min={1}
                    max={gridSize}
                    value={form.starting_position}
                    onChange={(e) => update("starting_position", Number(e.target.value))}
                    className={fieldClass}
                  />
                  <p className="text-sm text-neutral-500">Enter the car&apos;s current running position, P1-P{gridSize}.</p>
                </label>
                <label className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-300">Current tyre</span>
                  <select value={form.tyre_compound} onChange={(e) => update("tyre_compound", e.target.value)} className={fieldClass}>
                    {Object.keys(TYRE_LIFE).map((compound) => <option key={compound}>{compound}</option>)}
                  </select>
                </label>
              </div>

              {(driversError || (!driversLoading && drivers.length === 0)) && (
                <div className="mt-4">
                  <InlineNotice title="Driver Feed Unavailable" tone="warning">
                    Real driver standings are required before the simulator can run. Temporary roster labels are not used here.
                    <button onClick={() => void reloadDrivers()} className="ml-2 font-bold text-white underline decoration-white/30">Retry</button>
                  </InlineNotice>
                </div>
              )}
            </section>

            <section className="border-t border-white/10 pt-5">
              <StepHeading
                step="2"
                title="Set the stint state"
                detail="This is the core pit-wall question: how old are the tyres, and when are we testing the next stop?"
              />
              <div className="mt-4 flex flex-col gap-4">
                <SliderControl
                  label="Current lap"
                  value={form.current_lap}
                  min={1}
                  max={70}
                  display={`L${form.current_lap}`}
                  hint="Where the race is right now."
                  onChange={updateCurrentLap}
                />
                <SliderControl
                  label="Tyre age now"
                  value={form.tyre_age}
                  min={0}
                  max={50}
                  display={`${form.tyre_age} laps`}
                  hint="How many racing laps are already on this set."
                  onChange={(value) => update("tyre_age", value)}
                />
                <SliderControl
                  label="Test pit lap"
                  value={effectivePitLap}
                  min={Math.min(70, form.current_lap + 1)}
                  max={70}
                  display={`L${effectivePitLap}`}
                  hint="The stop lap you want the model to compare."
                  onChange={(value) => update("pit_lap", value)}
                />
              </div>

              <div className="mt-5 flex flex-col gap-2 sm:flex-row [&>*]:flex-1">
                <StintStat label="Tyre life" value={`${compoundLife} laps`} />
                <StintStat label="Age at stop" value={`${tyreAgeAtStop} laps`} tone={tyreAgeAtStop > compoundLife ? "warn" : "normal"} />
                <StintStat label="Life used" value={`${tyreLifeUsed}%`} tone={tyreLifeUsed > 100 ? "warn" : "normal"} />
              </div>
            </section>

            <section className="border-t border-white/10 pt-5">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <StepHeading
                  step="3"
                  title="Pick race assumptions"
                  detail="Start from a preset. Open advanced only when you want to tune traffic, safety-car, or rain risk."
                />
                <button
                  type="button"
                  onClick={() => setShowAdvanced((value) => !value)}
                  className="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-lg border border-white/12 px-4 text-sm font-semibold text-white transition-colors hover:border-[#00FF78]/55 hover:bg-[#00FF78]/10"
                >
                  <SlidersHorizontal className="h-4 w-4 text-[#00FF78]" />
                  {showAdvanced ? "Hide advanced" : "Advanced"}
                  <ChevronDown className={`h-4 w-4 transition-transform ${showAdvanced ? "rotate-180" : ""}`} />
                </button>
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {STRATEGY_PRESETS.map((preset) => (
                  <PresetButton
                    key={preset.key}
                    preset={preset}
                    selected={activePreset === preset.key}
                    onSelect={() => applyPreset(preset)}
                  />
                ))}
              </div>

              {showAdvanced ? (
                <div className="mt-5 flex flex-col gap-4 border-t border-white/10 pt-5">
                  <SliderControl
                    label="Rejoin traffic risk"
                    value={form.traffic_risk}
                    min={0}
                    max={100}
                    display={`${form.traffic_risk}%`}
                    hint="How likely the car is to rejoin behind slower traffic after the stop."
                    onChange={(value) => update("traffic_risk", value)}
                  />
                  <SliderControl
                    label="Safety-car probability"
                    value={form.safety_car_probability}
                    min={0}
                    max={100}
                    display={`${form.safety_car_probability}%`}
                    hint="Higher values make flexible stop timing more valuable."
                    onChange={(value) => update("safety_car_probability", value)}
                  />
                  <SliderControl
                    label="Rain risk"
                    value={form.weather_risk}
                    min={0}
                    max={100}
                    display={`${form.weather_risk}%`}
                    hint="Use this when the race could cross over to inters or wets."
                    onChange={(value) => update("weather_risk", value)}
                  />
                </div>
              ) : (
                <div className="mt-4 rounded-lg border border-white/10 bg-white/[0.025] px-4 py-3 text-sm leading-relaxed text-neutral-400">
                  Assumptions: {form.traffic_risk}% rejoin traffic, {form.safety_car_probability}% safety-car probability, {form.weather_risk}% rain risk.
                </div>
              )}
            </section>
          </div>

          <div className="mt-6 rounded-lg border border-[#3671C6]/35 bg-[#3671C6]/10 p-4">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#9EC5FF]" style={rcFont}>Simulation command</p>
                <h3 className="mt-1 text-xl font-semibold text-white" style={rcFont}>
                  {data?.recommendation.plan ? `${data.recommendation.plan} recommended` : "Ready to compare stop branches"}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-neutral-300">{runStatus}</p>
              </div>
              <div className="flex w-full flex-col gap-3 sm:flex-row xl:w-auto xl:shrink-0">
                <ScenarioChip label="Driver" value={effectiveDriver || "No driver"} />
                <ScenarioChip label="Tyre at stop" value={`${tyreAgeAtStop} laps`} />
                <button
                  onClick={() => void run()}
                  disabled={!canRun}
                  className="inline-flex h-12 min-w-[190px] items-center justify-center gap-2 rounded-lg bg-[#00FF78] px-5 text-sm font-semibold uppercase tracking-wider text-black transition-colors hover:bg-white disabled:cursor-not-allowed disabled:bg-white/15 disabled:text-neutral-500"
                >
                  <PlayCircle className="h-4 w-4" />
                  {isMutating ? "Running..." : data ? "Re-run simulation" : "Run simulation"}
                </button>
              </div>
            </div>
          </div>
        </Panel>

        <section className="space-y-5 min-w-0">
          {isMutating ? (
            <SectionLoader
              title="Running strategy simulation"
              detail="Comparing tyre age, target stop lap, rejoin traffic, and one-stop versus two-stop branches."
            />
          ) : (
            <>
              <MetricRow className="mb-0">
                <MetricCard label="Recommended" value={data?.recommendation.plan ?? "Awaiting simulation"} sub={data?.recommendation.rationale ?? "Set stint state and run the branch comparison"} icon={Target} />
                <MetricCard label="Pit Window" value={data?.recommendation.pit_window ?? "Pending"} sub={data?.recommendation.confidence ? `${data.recommendation.confidence} confidence · ${data.recommendation.branch_delta} pt gap` : "Primary call"} icon={Timer} color="#FF8000" />
                <MetricCard
                  label="Tyre At Stop"
                  value={`${data?.stint?.tyre_age_at_stop ?? tyreAgeAtStop} laps`}
                  sub={data?.stint?.compound_reference_source ?? `${data?.stint?.compound_life ?? compoundLife}-lap planning baseline`}
                  icon={Gauge}
                  color="#3671C6"
                />
                <MetricCard label="Driver" value={effectiveDriver} sub={effectiveTeam} icon={UserRound} color="#BE3AFF" />
              </MetricRow>

              {(error || runError) && (
                <InlineNotice title="Simulation Unavailable" tone="error">
                  {runError ?? "The strategy model did not return a result for this scenario."}
                  <button onClick={() => void run()} className="ml-2 font-bold text-white underline decoration-white/30">Retry</button>
                </InlineNotice>
              )}

              <Panel className="p-5">
                <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-xs font-black uppercase tracking-[0.16em] text-neutral-400">Data Provenance</p>
                    <h2 className="mt-1 text-xl font-black text-white" style={rcFont}>
                      {data?.data_quality?.grade ?? "No strategy run yet"}
                    </h2>
                    <p className="mt-2 text-sm leading-relaxed text-neutral-400">
                      {data?.data_quality?.note ?? "Run the simulator to see which numbers are observed data and which are scenario inputs."}
                    </p>
                  </div>
                  <StatusPill color={data?.data_quality?.grade === "Data-backed" ? "#00FF78" : data?.data_quality?.grade === "Partial data" ? "#FFF200" : "#3671C6"}>
                    {data?.data_quality ? `${data.data_quality.observed_sources}/${data.data_quality.total_sources} sources` : "Awaiting run"}
                  </StatusPill>
                </div>
                {data?.data_sources?.length ? (
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                    {data.data_sources.map((source) => (
                      <SourceCard key={source.label} source={source} />
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-neutral-500">No source card is shown until the strategy model has run.</p>
                )}
              </Panel>

              <Panel className="p-5">
                <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-xs font-black uppercase tracking-[0.16em] text-neutral-400">Model Evidence</p>
                    <h2 className="mt-1 text-xl font-black text-white" style={rcFont}>Why The Branch Moves</h2>
                  </div>
                  <StatusPill color={data?.recommendation.confidence === "High" ? "#00FF78" : data?.recommendation.confidence === "Low" ? "#FFF200" : "#3671C6"}>
                    {data?.recommendation.confidence ?? "Awaiting run"}
                  </StatusPill>
                </div>
                {data?.model_inputs?.length ? (
                  <div className="flex flex-col gap-3 md:flex-row md:flex-wrap [&>*]:min-w-[220px] [&>*]:flex-1">
                    {data.model_inputs.map((input) => (
                      <ModelInputCard key={input.label} input={input} />
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-neutral-500">Run the simulation to see the tyre, traffic, undercut, and overcut inputs that drive the call.</p>
                )}
              </Panel>

              <div className="flex flex-col gap-5 lg:flex-row [&>*]:min-w-0 [&>*]:flex-1">
                {(data?.plans ?? [
                  { name: "One-stop", score: 0, expected_finish: "Pending", pit_window: "Set stint state", risk: "Draft", notes: ["Run the branch comparison to score tyre life, traffic, and safety-car exposure."] },
                  { name: "Two-stop", score: 0, expected_finish: "Pending", pit_window: "Set stint state", risk: "Draft", notes: ["Run the branch comparison to score tyre life, traffic, and safety-car exposure."] },
                ]).map((plan) => (
                  <PlanCard key={plan.name} plan={plan} selected={plan.name === data?.recommendation.plan} />
                ))}
              </div>

              <WorkspaceSplit className="xl:[&>*]:flex-1">
                <Panel className="p-5">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <p className="text-xs font-black uppercase tracking-[0.16em] text-neutral-400">Stint State</p>
                      <h2 className="mt-1 text-xl font-black text-white" style={rcFont}>Tyre Degradation Curve</h2>
                    </div>
                    <StatusPill color={tyreLifeUsed > 100 ? "#FFF200" : "#00FF78"}>{tyreLifeUsed}% life</StatusPill>
                  </div>
                  <TyreDegradationChart
                    tyreAge={form.tyre_age}
                    pitLap={effectivePitLap}
                    compoundLife={compoundLife}
                    color={tyreLifeUsed > 100 ? "#FFF200" : "#00FF78"}
                    height={160}
                  />
                  <div className="mt-4 space-y-3">
                    <ProgressRow label="Rejoin traffic risk" value={form.traffic_risk} max={100} display={`${form.traffic_risk}%`} color="#FF8000" />
                    <ProgressRow label="Safety-car probability" value={form.safety_car_probability} max={100} display={`${form.safety_car_probability}%`} color="#BE3AFF" />
                  </div>
                </Panel>

                <Panel className="p-5">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <p className="text-xs font-black uppercase tracking-[0.16em] text-neutral-400">Decision Gates</p>
                      <h2 className="mt-1 text-xl font-black text-white" style={rcFont}>Pit Wall Checks</h2>
                    </div>
                    <Timer className="h-5 w-5 text-[#00FF78]" />
                  </div>
                  <div className="space-y-3">
                    {(data?.decision_matrix ?? [
                      {
                        gate: "Undercut release",
                        status: `L${Math.max(form.current_lap + 1, effectivePitLap - 3)}-${effectivePitLap}`,
                        detail: form.traffic_risk > 60 ? "Hold unless rival boxes first; traffic risk is too high for a blind attack." : "Attack if rival gap is inside 2.5s and rejoin lane is clear.",
                      },
                      {
                        gate: "Tyre cliff",
                        status: `${tyreAgeAtStop} lap age`,
                        detail: tyreAgeAtStop > compoundLife ? "Do not extend the first stint; switch to two-stop or safety-car stop branch." : "Extension remains viable if lap-time loss stays under the pit-wall threshold.",
                      },
                      {
                        gate: "Safety car",
                        status: `${form.safety_car_probability}% probability`,
                        detail: form.safety_car_probability > 50 ? "Prepare opportunistic stop branch and protect double-stack gap." : "Keep base plan; safety-car branch remains secondary.",
                      },
                    ]).map((gate) => (
                      <DecisionGate key={gate.gate} gate={gate.gate} trigger={gate.status} decision={gate.detail} />
                    ))}
                  </div>
                </Panel>
              </WorkspaceSplit>

              <Panel className="p-5">
                <h2 className="text-xl font-black italic uppercase text-white mb-4" style={rcFont}>Evidence Board</h2>
                {data?.battle_cards?.length ? (
                  <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap [&>*]:min-w-[180px] [&>*]:flex-1">
                    {data.battle_cards.map((card) => (
                      <div key={card.label} className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
                        <p className="text-xs font-black uppercase tracking-[0.14em] text-neutral-400">{card.label}</p>
                        <p className="mt-2 text-2xl font-black text-white" style={rcFont}>{card.value}</p>
                        {card.call && <p className="mt-1 text-sm font-bold text-[#00FF78]">{card.call}</p>}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-neutral-500">Run a simulation to populate tyre margin, first-stop reference, stop tendency, and scenario risk.</p>
                )}
              </Panel>
            </>
          )}
        </section>
      </WorkspaceSplit>
    </div>
  );
}

function SliderControl({
  label,
  value,
  min,
  max,
  display,
  hint,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  display: string;
  hint?: string;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block pb-1">
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-300">{label}</span>
        <span className="text-sm font-mono text-neutral-300">{display}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-[#00FF78] focus-visible:outline-offset-4"
      />
      {hint && <p className="mt-1 text-sm leading-relaxed text-neutral-500">{hint}</p>}
    </label>
  );
}

function StepHeading({ step, title, detail }: { step: string; title: string; detail: string }) {
  return (
    <div className="flex min-w-0 gap-3">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded border border-[#00FF78]/35 bg-[#00FF78]/10 text-sm font-semibold text-[#00FF78]">
        {step}
      </span>
      <div className="min-w-0">
        <h3 className="text-base font-semibold text-white" style={rcFont}>{title}</h3>
        <p className="mt-1 text-sm leading-relaxed text-neutral-400">{detail}</p>
      </div>
    </div>
  );
}

function PresetButton({
  preset,
  selected,
  onSelect,
}: {
  preset: StrategyPreset;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`min-h-[86px] rounded-lg border p-4 text-left transition-colors ${
        selected ? "border-[#00FF78]/70 bg-[#00FF78]/10" : "border-white/10 bg-white/[0.025] hover:border-white/25"
      }`}
    >
      <span className="block text-sm font-semibold text-white" style={rcFont}>{preset.label}</span>
      <span className="mt-1 block text-sm leading-relaxed text-neutral-400">{preset.detail}</span>
      <span className="mt-2 block text-xs text-neutral-500">
        {preset.values.traffic_risk}% traffic · {preset.values.safety_car_probability}% SC · {preset.values.weather_risk}% rain
      </span>
    </button>
  );
}

function StintStat({ label, value, tone = "normal" }: { label: string; value: string; tone?: "normal" | "warn" }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.035] p-3">
      <p className="text-[11px] font-black uppercase tracking-[0.12em] text-neutral-400">{label}</p>
      <p className={`mt-1 text-lg font-black ${tone === "warn" ? "text-[#FFF200]" : "text-white"}`} style={rcFont}>{value}</p>
    </div>
  );
}

function ScenarioChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2 lg:min-w-[140px]">
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-neutral-500">{label}</p>
      <p className="mt-1 truncate text-sm font-bold text-white">{value}</p>
    </div>
  );
}

function SourceCard({ source }: { source: { label: string; status: string; value: string; source?: string | null } }) {
  const color = source.status === "available" || source.status === "observed"
    ? "#00FF78"
    : source.status === "baseline"
      ? "#FFF200"
      : "#737373";

  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <p className="text-xs font-black uppercase tracking-[0.14em] text-neutral-400">{source.label}</p>
        <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: color }} />
      </div>
      <p className="text-base font-semibold text-white" style={rcFont}>{source.value}</p>
      {source.source && <p className="mt-2 text-sm leading-relaxed text-neutral-500">{source.source}</p>}
    </div>
  );
}

function PlanCard({
  plan,
  selected,
}: {
  plan: { name: string; score: number; expected_finish: string; pit_window: string; risk: string; notes: string[] };
  selected: boolean;
}) {
  return (
    <Panel className="p-5 h-full" accent={selected ? "#00FF78" : "#3671C6"}>
      <div className="mb-5 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-black italic uppercase text-white leading-none" style={rcFont}>{plan.name}</h2>
          <p className="mt-2 text-sm text-neutral-500">{plan.expected_finish} · {plan.pit_window}</p>
        </div>
        <StatusPill color={plan.risk === "High" ? "#E10600" : plan.risk === "Low" ? "#00FF78" : "#FFF200"}>{plan.risk}</StatusPill>
      </div>
      <div className="mb-5">
        <div className="mb-1 flex justify-between text-xs">
          <span className="font-black uppercase text-neutral-500">Viability index</span>
          <span className="font-mono text-neutral-300">{plan.score}</span>
        </div>
        <div className="h-2 overflow-hidden rounded bg-white/8">
          <div className="h-full rounded bg-[#00FF78]" style={{ width: `${Math.max(0, Math.min(100, plan.score))}%` }} />
        </div>
      </div>
      <ul className="space-y-2">
        {plan.notes.map((note) => (
          <li key={note} className="flex gap-2 text-sm leading-relaxed text-neutral-400">
            <Gauge className="mt-0.5 h-4 w-4 shrink-0 text-neutral-600" />
            {note}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function ModelInputCard({
  input,
}: {
  input: { label: string; value: string; impact: string; source: string; tone: "good" | "warning" | "critical" };
}) {
  const color = input.tone === "critical" ? "#E10600" : input.tone === "warning" ? "#FFF200" : "#00FF78";
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.14em] text-neutral-400">{input.label}</p>
          <p className="mt-1 text-2xl font-black text-white" style={rcFont}>{input.value}</p>
        </div>
        <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: color }} />
      </div>
      <p className="text-sm leading-relaxed text-neutral-300">{input.impact}</p>
      <p className="mt-2 text-xs text-neutral-500">{input.source}</p>
    </div>
  );
}

function ProgressRow({
  label,
  value,
  max,
  display,
  color,
}: {
  label: string;
  value: number;
  max: number;
  display: string;
  color: string;
}) {
  const width = Math.max(2, Math.min(100, (value / max) * 100));
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-3">
        <span className="text-sm font-bold text-neutral-300">{label}</span>
        <span className="font-mono text-xs text-neutral-500">{display}</span>
      </div>
      <div className="h-2 overflow-hidden rounded bg-white/10">
        <div className="h-full rounded" style={{ width: `${width}%`, background: color }} />
      </div>
    </div>
  );
}

function DecisionGate({ gate, trigger, decision }: { gate: string; trigger: string; decision: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <p className="text-sm font-bold text-white">{gate}</p>
        <span className="font-mono text-xs text-[#00FF78]">{trigger}</span>
      </div>
      <p className="text-sm leading-relaxed text-neutral-400">{decision}</p>
    </div>
  );
}
