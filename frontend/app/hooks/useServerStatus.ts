"use client";

import { useEffect, useSyncExternalStore } from "react";

import {
  getServerStatus,
  getServerStatusOnServer,
  startServerProbe,
  subscribeServerStatus,
  type ServerState,
} from "../lib/serverStatus";

export type { ServerState, ServerStatus } from "../lib/serverStatus";

/**
 * Reports whether the backend has finished starting (a restart or Render's cold start).
 *
 * Starts as 'unknown' rather than optimistically 'warming', so a server that is
 * up never flashes the restart notice: the first probe resolves straight to
 * 'ready' and nothing is ever shown.
 */
export function useServerStatus(): ServerState {
  useEffect(() => {
    startServerProbe();
  }, []);
  return useSyncExternalStore(subscribeServerStatus, getServerStatus, getServerStatusOnServer);
}
