import { API_BASE } from "../constants/api";

export type ServerStatus = "unknown" | "warming" | "ready" | "unreachable";

export interface ServerState {
  status: ServerStatus;
  /** Human-readable description of the current warm-up step, when warming. */
  detail: string | null;
  /** Backend warm-up stage id, used to drive the start-light progress. */
  stage: string | null;
  /**
   * Counts probe runs. Lets the UI scope per-run state — a dismissal, the
   * lights-out moment — to one run, so a later restart shows again.
   */
  run: number;
  /**
   * True once the current run has seen the server warming. Distinguishes "was
   * already up" from "came back while you waited", so a server that is up
   * never flashes anything.
   */
  waited: boolean;
}

interface ReadyResponse {
  ready: boolean;
  stage: string | null;
  detail: string | null;
}

/** A probe with no answer by now has failed: the server is down or restarting. */
const PROBE_TIMEOUT_MS = 4000;
const PROBE_INTERVAL_MS = 3000;
/**
 * Give up after two minutes. A restart after a deploy is ready well inside
 * this, and the deploy itself rolls back when `/api/ready` has not answered
 * ready within 120 s, so past it the server is down, not restarting.
 */
const GIVE_UP_MS = 120_000;
/** A failed request this soon after a probe said "ready" is not worth another probe. */
const RECHECK_COOLDOWN_MS = 10_000;

const INITIAL_STATE: ServerState = {
  status: "unknown",
  detail: null,
  stage: null,
  run: 0,
  waited: false,
};

/**
 * Module-level store so every consumer shares one probe cycle.
 *
 * The probe hits /api/ready rather than /api/health deliberately. Health answers
 * "is the process up?", which goes true within a second of a restart while the
 * model and database are still loading. Readiness tracks the thing a data
 * request actually needs.
 *
 * The backend is always on, so the probe normally answers "ready" at once and
 * nothing is shown. Only a probe that fails — no answer, an error status, or a
 * report that says not ready — counts as not ready; a slow answer that says
 * ready is ready.
 */
let state: ServerState = INITIAL_STATE;
const listeners = new Set<() => void>();
let started = false;
let probing = false;
let runStartedAt = 0;
let lastReadyAt = 0;

/** Publishes a new snapshot. Always builds a fresh object — never mutates. */
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

/** The server renders no status notice; readiness is a client-only concern. */
export function getServerStatusOnServer(): ServerState {
  return INITIAL_STATE;
}

const textOrNull = (value: unknown): string | null => (typeof value === "string" ? value : null);

/** Reads a `/api/ready` body, or null when it is not a readiness report. */
function parseReadiness(body: unknown): ReadyResponse | null {
  if (typeof body !== "object" || body === null) return null;
  const { ready, stage, detail } = body as Record<string, unknown>;
  if (typeof ready !== "boolean") return null;
  return { ready, stage: textOrNull(stage), detail: textOrNull(detail) };
}

async function fetchReadiness(): Promise<ReadyResponse | null> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}/api/ready`, { signal: controller.signal });
    if (!res.ok) return null;
    return parseReadiness(await res.json());
  } catch {
    // Timeout, network error, or a body that is not JSON: the server is not up.
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

function markWarming(readiness: ReadyResponse | null): void {
  publish({
    status: "warming",
    detail: readiness?.detail ?? null,
    stage: readiness?.stage ?? null,
    waited: true,
  });
}

function finishRun(status: "ready" | "unreachable", stage: string | null): void {
  probing = false;
  if (status === "ready") lastReadyAt = Date.now();
  publish({ status, detail: null, stage });
}

async function poll(): Promise<void> {
  const readiness = await fetchReadiness();

  if (readiness?.ready) {
    finishRun("ready", readiness.stage);
    return;
  }
  if (Date.now() - runStartedAt >= GIVE_UP_MS) {
    // Stop rather than claim "updating" forever against a dead server.
    finishRun("unreachable", null);
    return;
  }

  markWarming(readiness);
  setTimeout(() => void poll(), PROBE_INTERVAL_MS);
}

/**
 * Starts a probe run unless one is already looking.
 *
 * The status is left as it was until the probe answers, so a recheck against a
 * server that is up changes nothing a consumer can see.
 */
function startRun(): void {
  if (probing) return;
  probing = true;
  runStartedAt = Date.now();
  publish({ run: state.run + 1, waited: false });
  void poll();
}

/**
 * Asks the probe to look again because something suggests the server went away.
 *
 * Ignored before the first run (including during server rendering), while
 * offline — no connection is not a restart, and coming back online rechecks on
 * its own — and just after a run confirmed the server ready.
 */
export function recheckServer(): void {
  if (!started) return;
  if (!navigator.onLine) return;
  if (Date.now() - lastReadyAt < RECHECK_COOLDOWN_MS) return;
  startRun();
}

/**
 * Probes again on the user's say-so, bypassing the automatic guards. Shows
 * warming at once, so the button visibly does something before the probe lands.
 */
export function retryServerProbe(): void {
  startRun();
  markWarming(null);
}

function onPageShow(event: PageTransitionEvent): void {
  // A page restored from the back/forward cache keeps its old "ready" verdict.
  if (event.persisted) recheckServer();
}

/**
 * Listens for the moments a "ready" verdict may have gone stale without any
 * request failing: a back/forward-cache restore, and the device coming back
 * online. A failed data request asks for a recheck itself (`fetcher.ts`).
 * Installed once for the life of the page.
 */
function installRecheckTriggers(): void {
  window.addEventListener("pageshow", onPageShow);
  window.addEventListener("online", recheckServer);
}

/** Starts the first probe run and the recheck triggers. Idempotent. */
export function startServerProbe(): void {
  if (started) return;
  started = true;
  installRecheckTriggers();
  startRun();
}
