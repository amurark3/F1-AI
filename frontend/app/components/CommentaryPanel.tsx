"use client";

import { motion, AnimatePresence } from "framer-motion";

import type { CommentaryEntry } from "../hooks/useLiveTiming";

interface Props {
  entries: CommentaryEntry[];
}

const EVENT_STYLES: Record<string, { label: string; colorClass: string }> = {
  safety_car: { label: "SC", colorClass: "text-yellow-400 border-yellow-400/30" },
  position_change: { label: "POS", colorClass: "text-blue-400 border-blue-400/30" },
  pit_stop: { label: "PIT", colorClass: "text-orange-400 border-orange-400/30" },
};
const DEFAULT_STYLE = { label: "RC", colorClass: "text-neutral-400 border-white/10" };

function formatTime(isoString: string): string {
  try {
    return new Date(isoString).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "--:--";
  }
}

export default function CommentaryPanel({ entries }: Props) {
  return (
    <div className="glass rounded-xl p-4 h-full flex flex-col">
      <h2 className="text-xs font-black uppercase tracking-widest text-neutral-400 mb-3">Strategy Commentary</h2>

      {entries.length === 0 ? (
        <p className="text-neutral-500 text-sm text-center py-8">
          No commentary yet. Commentary appears during live events.
        </p>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-3">
          <AnimatePresence initial={false}>
            {entries.map((entry) => {
              const style = EVENT_STYLES[entry.event_type] ?? DEFAULT_STYLE;
              return (
                <motion.div
                  key={entry.id}
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2, ease: "easeOut" }}
                  className={`border rounded-xl p-3 ${style.colorClass}`}
                >
                  <div className="flex items-start gap-2">
                    <span
                      className="text-[10px] font-black leading-none mt-0.5 shrink-0 rounded border border-current px-1.5 py-1"
                      aria-hidden="true"
                    >
                      {style.label}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm leading-snug">{entry.text}</p>
                      <span className="text-xs opacity-50 font-mono mt-1 block">{formatTime(entry.timestamp)}</span>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
