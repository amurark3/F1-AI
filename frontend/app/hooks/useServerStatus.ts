"use client";

import { useState, useEffect } from 'react';
import { API_BASE } from '../constants/api';

export type ServerStatus = 'unknown' | 'warming' | 'ready';

// Module-level cache so all consumers share one probe cycle per page load
let cachedStatus: ServerStatus = 'unknown';
const listeners = new Set<(s: ServerStatus) => void>();

function notify(status: ServerStatus) {
  cachedStatus = status;
  listeners.forEach((fn) => fn(status));
}

let probeStarted = false;

async function probe() {
  if (probeStarted) return;
  probeStarted = true;
  notify('warming');

  const poll = async () => {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 3000);
      const res = await fetch(`${API_BASE}/api/health`, { signal: controller.signal });
      clearTimeout(timeout);
      if (res.ok) {
        notify('ready');
        return; // done
      }
    } catch {
      // timeout or network error — server still cold
    }
    setTimeout(poll, 4000); // retry in 4s
  };

  poll();
}

export function useServerStatus(): { status: ServerStatus; isWarming: boolean } {
  const [status, setStatus] = useState<ServerStatus>(cachedStatus);

  useEffect(() => {
    const listener = (s: ServerStatus) => setStatus(s);
    listeners.add(listener);
    // Start probing if not already started
    probe();
    return () => { listeners.delete(listener); };
  }, []);

  return { status, isWarming: status === 'warming' };
}
