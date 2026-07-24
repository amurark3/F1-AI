"use client";

import { useEffect, useSyncExternalStore } from 'react';

import { API_BASE } from '../constants/api';

export type ServerStatus = 'unknown' | 'warming' | 'ready' | 'unreachable';

export interface ServerState {
  status: ServerStatus;
  /** Human-readable description of the current warm-up step, when warming. */
  detail: string | null;
  /** Backend warm-up stage id, used to drive the start-light progress. */
  stage: string | null;
  isWarming: boolean;
  /**
   * True once this page load has seen the server warming at least once. Lets the
   * UI distinguish "was already warm" from "finished warming while you waited",
   * so a warm server never flashes anything.
   */
  everWarmed: boolean;
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

const INITIAL_STATE: ServerState = {
  status: 'unknown',
  detail: null,
  stage: null,
  isWarming: false,
  everWarmed: false,
};

/**
 * Module-level cache so every consumer shares one probe cycle per page load.
 *
 * The probe hits /api/ready rather than /api/health deliberately. Health answers
 * "is the process up?", which on Render goes true within a second of the container
 * waking while the model and database are still loading — hiding the banner long
 * before the app can actually answer a data request. Readiness tracks the thing
 * the user is really waiting for.
 *
 * The probe doubles as the wake-up knock: any request to a spun-down Render
 * instance starts the container, which starts its warm-up. Because this hook is
 * mounted from the root layout, landing on any page — including the static
 * homepage — triggers that.
 */
let cachedState: ServerState = INITIAL_STATE;
const listeners = new Set<() => void>();
let probeStarted = false;
let hasEverWarmed = false;

/** Publishes a new snapshot. Always builds a fresh object — never mutates. */
function notify(state: Omit<ServerState, 'everWarmed'>): void {
  if (state.isWarming) hasEverWarmed = true;
  cachedState = { ...state, everWarmed: hasEverWarmed };
  listeners.forEach((listener) => listener());
}

function subscribe(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange);
  return () => { listeners.delete(onStoreChange); };
}

/** Reference is stable between notifications, as useSyncExternalStore requires. */
function getSnapshot(): ServerState {
  return cachedState;
}

/** The server renders no banner; readiness is a client-only concern. */
function getServerSnapshot(): ServerState {
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

function startProbing(): void {
  if (probeStarted) return;
  probeStarted = true;

  let attempts = 0;

  const poll = async (): Promise<void> => {
    attempts += 1;
    const readiness = await fetchReadiness();

    if (readiness?.ready) {
      notify({ status: 'ready', detail: null, stage: readiness.stage, isWarming: false });
      return;
    }

    if (attempts >= MAX_ATTEMPTS) {
      // Stop rather than claim "warming up" forever against a dead server.
      notify({ status: 'unreachable', detail: null, stage: null, isWarming: false });
      return;
    }

    notify({
      status: 'warming',
      detail: readiness?.detail ?? null,
      stage: readiness?.stage ?? null,
      isWarming: true,
    });
    setTimeout(() => void poll(), PROBE_INTERVAL_MS);
  };

  void poll();
}

/**
 * Reports whether the backend has finished warming up.
 *
 * Starts as 'unknown' rather than optimistically 'warming', so a server that is
 * already warm never flashes a banner — the first probe resolves straight to
 * 'ready' and nothing is ever shown.
 */
export function useServerStatus(): ServerState {
  useEffect(() => { startProbing(); }, []);
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
