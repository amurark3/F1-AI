import { API_BASE } from "../constants/api";

export type ServerStatus = "unknown" | "warming" | "ready" | "unreachable";

export interface ServerState {
  status: ServerStatus;
  /** The backend's description of the current warm-up step, from the last answer that had one. */
  detail: string | null;
  /** Backend warm-up stage id, from the last answer. */
  stage: string | null;
  /** How many of the five start lights are lit: the highest count this run has reached. */
  lit: number;
  /**
   * Counts probe runs. Lets the UI scope per-run state (a dismissal, the
   * lights-out moment) to one run, so a later restart shows again.
   */
  run: number;
  /**
   * True once the current run has seen the server not ready. Distinguishes
   * "was already up" from "finished starting while you watched", so a server
   * that is up never flashes anything.
   */
  waited: boolean;
  /** Epoch ms at which the current run first saw the server not ready. */
  warmingSince: number | null;
  /** The run whose unreachable notice the visitor dismissed. */
  dismissedRun: number;
  /** The run whose "back online" moment has finished. */
  launchedRun: number;
}

interface ReadyResponse {
  ready: boolean;
  stage: string;
  detail: string;
}

/**
 * Backend warm-up stages, in the order the server runs them (`WARMUP_STEPS` in
 * backend/app/services/readiness.py, after `pending`). The stage in progress
 * sets how many start lights are lit, so the lights fill as real work
 * completes, never on a timer.
 */
export const STAGE_ORDER: readonly string[] = ["pending", "database", "model", "season", "store"];
export const LIGHT_COUNT = STAGE_ORDER.length;

/** How long the "back online" moment holds before the notice goes. */
export const LAUNCH_DURATION_MS = 1200;

export const PROBE_TIMEOUT_MS = 4000;
const PROBE_INTERVAL_MS = 3000;
/** A restart or a Render cold start (about a minute) is over well inside this; past it the server is down. */
export const GIVE_UP_MS = 120_000;
/** A failed request this soon after a probe said "ready" is not worth another probe. */
const RECHECK_COOLDOWN_MS = 10_000;

const INITIAL_STATE: ServerState = {
  status: "unknown",
  detail: null,
  stage: null,
  lit: 0,
  run: 0,
  waited: false,
  warmingSince: null,
  dismissedRun: 0,
  launchedRun: 0,
};

/**
 * How many lights are lit, given the readiness answer and the count the run
 * has already reached. Ready lights all five. A stage in progress sets its
 * count (`pending` 1 to `store` 5). An unknown stage, or no answer at all
 * (`stage` null), keeps what the run reached, with a floor of one so the
 * lights never go out mid-restart. The count never drops within a run.
 */
export function lightsFor(stage: string | null, ready: boolean, reached = 0): number {
  if (ready) return LIGHT_COUNT;
  const fromStage = stage === null ? 0 : STAGE_ORDER.indexOf(stage) + 1;
  return Math.max(1, reached, fromStage);
}

/**
 * Module-level store so every consumer shares one probe cycle.
 *
 * The probe hits /api/ready rather than /api/health deliberately: health says
 * the process is up, which goes true while the model and database are still
 * loading. Readiness tracks what the visitor is really waiting for. Only a
 * failed probe counts as not ready; a slow one is just waiting.
 *
 * The probe doubles as the wake-up knock for a Render instance that spun down.
 */
let state: ServerState = INITIAL_STATE;
const listeners = new Set<() => void>();
let started = false;
let probing = false;
let lastReadyAt = 0;
let runStartedAt = 0;

/** Publishes a new snapshot. Always builds a fresh object, never mutates. */
function publish(patch: Partial<ServerState>): void {
  state = { ...state, ...patch };
  listeners.forEach((listener) => listener());
}

export function subscribeServerStatus(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange);
  return () => {
    listeners.delete(onStoreChange);
  };
}

/** Reference is stable between publishes, as useSyncExternalStore requires. */
export function getServerStatus(): ServerState {
  return state;
}

/** The server renders no notice; readiness is a client-only concern. */
export function getServerStatusOnServer(): ServerState {
  return INITIAL_STATE;
}

/** The readiness body, or null when it is not the documented shape. Never trusts the wire. */
export function parseReadiness(body: unknown): ReadyResponse | null {
  if (typeof body !== "object" || body === null) return null;
  const { ready, stage, detail } = body as Record<string, unknown>;
  if (typeof ready !== "boolean" || typeof stage !== "string" || typeof detail !== "string") return null;
  return { ready, stage, detail };
}

async function fetchReadiness(): Promise<ReadyResponse | null> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}/api/ready`, { signal: controller.signal });
    if (!res.ok) return null;
    return parseReadiness(await res.json());
  } catch {
    // Timeout, network error, bad JSON, or a container that has not woken yet.
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

function markWarming(readiness: ReadyResponse | null): void {
  publish({
    status: "warming",
    detail: readiness?.detail ?? state.detail,
    stage: readiness?.stage ?? state.stage,
    lit: lightsFor(readiness?.stage ?? null, false, state.lit),
    waited: true,
    warmingSince: state.warmingSince ?? Date.now(),
  });
}

function finishReady(readiness: ReadyResponse): void {
  probing = false;
  lastReadyAt = Date.now();
  const { run, waited } = state;
  publish({ status: "ready", detail: null, stage: readiness.stage, lit: lightsFor(readiness.stage, true) });
  // The "back online" moment ends on its own clock; only a run that waited has one.
  if (waited) setTimeout(() => publish({ launchedRun: run }), LAUNCH_DURATION_MS);
}

async function poll(): Promise<void> {
  const readiness = await fetchReadiness();

  if (readiness?.ready) {
    finishReady(readiness);
    return;
  }
  if (Date.now() - runStartedAt >= GIVE_UP_MS) {
    // Stop rather than claim "starting" forever against a dead server.
    probing = false;
    publish({ status: "unreachable", detail: null });
    return;
  }

  markWarming(readiness);
  setTimeout(() => void poll(), PROBE_INTERVAL_MS);
}

/**
 * Starts a probe run unless one is already looking. The status is left as it
 * was until the probe answers, so a recheck against a server that is up
 * changes nothing a consumer can see. `keepLights` carries the reached count
 * across a visitor's retry.
 */
function startRun(keepLights: boolean): void {
  if (probing) return;
  probing = true;
  runStartedAt = Date.now();
  publish({ run: state.run + 1, waited: false, warmingSince: null, lit: keepLights ? state.lit : 0 });
  void poll();
}

/**
 * Asks the probe to look again because something suggests the server went away.
 *
 * Ignored before the first run (including during server rendering), while
 * offline (no connection is not a restart; coming back online rechecks on its
 * own) and just after a run confirmed the server ready.
 */
export function recheckServer(): void {
  if (!started) return;
  if (!navigator.onLine) return;
  if (Date.now() - lastReadyAt < RECHECK_COOLDOWN_MS) return;
  startRun(false);
}

/** Probes again on the visitor's say-so, bypassing the automatic guards. */
export function retryServerProbe(): void {
  startRun(true);
  markWarming(null);
}

/** Hides the unreachable notice for the current run. */
export function dismissServerNotice(): void {
  publish({ dismissedRun: state.run });
}

function onPageShow(event: PageTransitionEvent): void {
  // A page restored from the back/forward cache keeps its old "ready" verdict.
  if (event.persisted) recheckServer();
}

/** Starts the first probe run and the recheck triggers. Idempotent. */
export function startServerProbe(): void {
  if (started) return;
  started = true;
  window.addEventListener("pageshow", onPageShow);
  window.addEventListener("online", recheckServer);
  startRun(false);
}

export type NoticePhase = "warming" | "unreachable" | "launching";

/** What the notice shows now; null while the backend is up. */
export function noticePhase(server: ServerState): NoticePhase | null {
  if (server.status === "warming") return "warming";
  if (server.status === "unreachable") return server.dismissedRun === server.run ? null : "unreachable";
  if (server.status === "ready" && server.waited && server.launchedRun !== server.run) return "launching";
  return null;
}
