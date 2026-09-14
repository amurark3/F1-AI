"use client";

import { useState, useEffect, useRef } from "react";

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

export interface CommentaryEntry {
  id: string;
  text: string;
  event_type: string;
  timestamp: string;
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
  | { type: "positions"; data: LivePosition[] }
  | { type: "session_status"; data: SessionStatus }
  | { type: "commentary"; data: CommentaryEntry }
  | { type: "ping" };

/** Max commentary entries retained in memory. */
const MAX_COMMENTARY = 100;

export function useLiveTiming(year: number, round: number) {
  const [positions, setPositions] = useState<LivePosition[]>([]);
  const [sessionStatus, setSessionStatus] = useState<SessionStatus | null>(null);
  const [commentary, setCommentary] = useState<CommentaryEntry[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    // Don't open a WebSocket for invalid year/round (e.g. no live race)
    if (!year || !round) return;

    const wsBase = API_BASE.replace(/^https/, "wss").replace(/^http/, "ws");
    const url = `${wsBase}/api/live/${year}/${round}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
    };

    ws.onclose = () => {
      setIsConnected(false);
    };

    ws.onerror = () => {
      setIsConnected(false);
    };

    ws.onmessage = (event: MessageEvent) => {
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
          case "commentary":
            setCommentary((prev) => [msg.data, ...prev].slice(0, MAX_COMMENTARY));
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

    return () => {
      setPositions([]);
      setSessionStatus(null);
      ws.close();
    };
  }, [year, round]);

  return { positions, sessionStatus, commentary, isConnected };
}
