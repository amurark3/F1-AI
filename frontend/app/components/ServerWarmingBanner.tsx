"use client";

import { useServerStatus } from '../hooks/useServerStatus';

export default function ServerWarmingBanner() {
  const { isWarming } = useServerStatus();

  if (!isWarming) return null;

  return (
    <div className="flex items-center gap-2 px-4 py-2.5 bg-neutral-800/60 border-b border-white/5 text-sm text-neutral-400">
      <div className="w-3 h-3 rounded-full border-2 border-neutral-400 border-t-transparent animate-spin" />
      Warming up server — this may take up to 60 seconds on first load
    </div>
  );
}
