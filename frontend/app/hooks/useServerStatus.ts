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
 * Reports whether the backend has finished warming up.
 *
 * Starts as 'unknown' rather than optimistically 'warming', so a server that is
 * already warm never flashes the warm-up screen — the first probe resolves
 * straight to 'ready' and nothing is ever shown.
 */
export function useServerStatus(): ServerState {
  useEffect(() => {
    startServerProbe();
  }, []);
  return useSyncExternalStore(subscribeServerStatus, getServerStatus, getServerStatusOnServer);
}
