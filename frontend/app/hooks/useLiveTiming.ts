"use client";

import { useState, useEffect } from "react";

import { API_BASE } from "../constants/api";

export interface LivePosition {
  position: number;
  driver: string;
  driver_number: number;
  team: string | null;
  gap: string;
  last_lap: string | null;
  pit_stops: number | null;
}

/**
 * `live` is only ever reported once the feed for *this* session has opened —
 * an open session window alone reports `standby`. A `standby` that still
 * carries a `session_name` means the session is under way and the desk is
 * waiting on OpenF1, which is a different thing from an empty track.
 */
export type SessionState = "live" | "standby" | "finished";

export interface SessionStatus {
  status: SessionState;
  /** "Race", "Sprint", "Qualifying", "Practice 2" — null when nothing is running. */
  session_name: string | null;
  meeting_name: string | null;
  starts_at: string | null;
  /** Null when the lap count is unknown; OpenF1 publishes no total-lap figure. */
  lap: number | null;
  /**
   * Seconds since the newest sample behind the current rows, or null when no
   * feed is open. A quiet feed is normal — the order simply held — so the
   * tower keeps its rows and reports the age instead of blanking.
   */
  feed_age_seconds: number | null;
}

/** Messages pushed over the live-timing WebSocket. */
type LiveMessage =
  { type: "positions"; data: LivePosition[] } | { type: "session_status"; data: SessionStatus } | { type: "ping" };

/** First reconnect delay after the socket drops; it doubles per failed try. */
const RECONNECT_BASE_MS = 1_000;
/** Longest wait between reconnect tries, so a long outage still recovers within this. */
const RECONNECT_MAX_MS = 30_000;

/** Delay before reconnect try `attempt` (0-based): 1 s, 2 s, 4 s … capped. */
const reconnectDelay = (attempt: number): number => Math.min(RECONNECT_BASE_MS * 2 ** attempt, RECONNECT_MAX_MS);

export function useLiveTiming(year: number, round: number) {
  const [positions, setPositions] = useState<LivePosition[]>([]);
  const [sessionStatus, setSessionStatus] = useState<SessionStatus | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    // Don't open a WebSocket for invalid year/round (e.g. no live race)
    if (!year || !round) return;

    const wsBase = API_BASE.replace(/^https/, "wss").replace(/^http/, "ws");
    const url = `${wsBase}/api/live/${year}/${round}`;

    let ws: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;
    let disposed = false;

    // A dropped socket (deploy, network blip, proxy timeout) reopens on its
    // own; without this the tower sat on "Connecting…" until the round changed.
    const connect = () => {
      const socket = new WebSocket(url);
      ws = socket;

      socket.onopen = () => {
        attempt = 0;
        setIsConnected(true);
      };

      socket.onclose = () => {
        setIsConnected(false);
        if (disposed || socket !== ws) return;
        retryTimer = setTimeout(connect, reconnectDelay(attempt));
        attempt += 1;
      };

      socket.onerror = () => {
        setIsConnected(false);
      };

      socket.onmessage = handleMessage;
    };

    const handleMessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data as string) as LiveMessage;
        switch (msg.type) {
          case "positions":
            setPositions(msg.data);
            break;
          case "session_status":
            setSessionStatus(msg.data);
            if (msg.data.status !== "live") setPositions([]);
            break;
          case "ping":
            // ignore heartbeat
            break;
          default:
            break;
        }
      } catch {
        // ignore malformed messages
      }
    };

    connect();

    return () => {
      disposed = true;
      clearTimeout(retryTimer);
      setPositions([]);
      setSessionStatus(null);
      ws?.close();
    };
  }, [year, round]);

  return { positions, sessionStatus, isConnected };
}
