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
   * lights-out moment — to one run, so a later cold restart shows again.
   */
  run: number;
  /**
   * True once the current run has seen the server warming. Distinguishes "was
   * already warm" from "finished warming while you waited", so a warm server
   * never flashes anything.
   */
  waited: boolean;
  /** Epoch ms at which the current run first saw the server warming. */
  warmingSince: number | null;
}

interface ReadyResponse {
  ready: boolean;
  stage: string;
  detail: string;
}

const PROBE_TIMEOUT_MS = 4000;
const PROBE_INTERVAL_MS = 3000;
/** Give up after ~3 minutes. A cold start is ~50s; past this the server is down. */
const MAX_ATTEMPTS = 60;
/**
 * A warm server answers /api/ready well inside this. A first probe still
 * pending past it is being held by Render while the container boots, so the
 * warm-up screen goes up now rather than when the probe finally times out.
 */
const SLOW_PROBE_MS = 1500;
/** A tab hidden this long may come back to a server that spun down or restarted. */
const STALE_TAB_MS = 60_000;
/** A failed request this soon after a probe said "ready" is not worth another probe. */
const RECHECK_COOLDOWN_MS = 10_000;

const INITIAL_STATE: ServerState = {
  status: "unknown",
  detail: null,
  stage: null,
  run: 0,
  waited: false,
  warmingSince: null,
};

/**
 * Module-level store so every consumer shares one probe cycle.
 *
 * The probe hits /api/ready rather than /api/health deliberately. Health answers
 * "is the process up?", which on Render goes true within a second of the container
 * waking while the model and database are still loading — dropping the warm-up
 * screen long before the app can actually answer a data request. Readiness
 * tracks the thing the user is really waiting for.
 *
 * The probe doubles as the wake-up knock: any request to a spun-down Render
 * instance starts the container, which starts its warm-up. Because the probe is
 * started from the root layout, landing on any page triggers that.
 */
let state: ServerState = INITIAL_STATE;
const listeners = new Set<() => void>();
let started = false;
let probing = false;
let lastReadyAt = 0;
let hiddenAt: number | null = null;

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

/** The server renders no warm-up screen; readiness is a client-only concern. */
export function getServerStatusOnServer(): ServerState {
  return INITIAL_STATE;
}

async function fetchReadiness(): Promise<ReadyResponse | null> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}/api/ready`, { signal: controller.signal });
    if (!res.ok) return null;
    return (await res.json()) as ReadyResponse;
  } catch {
    // Timeout, network error, or a container that has not woken yet.
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
    warmingSince: state.warmingSince ?? Date.now(),
  });
}

function finishRun(status: "ready" | "unreachable", stage: string | null): void {
  probing = false;
  if (status === "ready") lastReadyAt = Date.now();
  publish({ status, detail: null, stage });
}

async function poll(attempt: number): Promise<void> {
  const slowProbe = attempt === 1 ? setTimeout(() => markWarming(null), SLOW_PROBE_MS) : undefined;
  const readiness = await fetchReadiness();
  clearTimeout(slowProbe);

  if (readiness?.ready) {
    finishRun("ready", readiness.stage);
    return;
  }
  if (attempt >= MAX_ATTEMPTS) {
    // Stop rather than claim "warming up" forever against a dead server.
    finishRun("unreachable", null);
    return;
  }

  markWarming(readiness);
  setTimeout(() => void poll(attempt + 1), PROBE_INTERVAL_MS);
}

/**
 * Starts a probe run unless one is already looking.
 *
 * The status is left as it was until the probe answers (or is slow to), so a
 * recheck against a warm server changes nothing a consumer can see.
 */
function startRun(): void {
  if (probing) return;
  probing = true;
  publish({ run: state.run + 1, waited: false, warmingSince: null });
  void poll(1);
}

/**
 * Asks the probe to look again because something suggests the server went away.
 *
 * Ignored before the first run (including during server rendering), while
 * offline — no connection is not a cold start, and coming back online
 * rechecks on its own — and just after a run confirmed the server ready.
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

function onVisibilityChange(): void {
  if (document.visibilityState === "hidden") {
    hiddenAt = Date.now();
    return;
  }
  const wasStale = hiddenAt !== null && Date.now() - hiddenAt >= STALE_TAB_MS;
  hiddenAt = null;
  if (wasStale) recheckServer();
}

function onPageShow(event: PageTransitionEvent): void {
  // A page restored from the back/forward cache keeps its old "ready" verdict.
  if (event.persisted) recheckServer();
}

/**
 * Listens for the moments a server that was ready may have gone cold: a tab
 * left in the background past Render's idle spin-down (the common mobile
 * case), a back/forward-cache restore, and the device coming back online.
 * Installed once for the life of the page.
 */
function installRecheckTriggers(): void {
  document.addEventListener("visibilitychange", onVisibilityChange);
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
