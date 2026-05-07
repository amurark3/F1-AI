"use client";

import { motion, AnimatePresence } from "framer-motion";
import { CommentaryEntry } from "../hooks/useLiveTiming";

interface Props {
  entries: CommentaryEntry[];
}

const EVENT_STYLES: Record<string, { icon: string; colorClass: string }> = {
  safety_car:      { icon: "\u26a0",  colorClass: "text-yellow-400 border-yellow-400/30" },
  position_change: { icon: "\u2191\u2193", colorClass: "text-blue-400 border-blue-400/30" },
  pit_stop:        { icon: "\uD83D\uDD27", colorClass: "text-orange-400 border-orange-400/30" },
};
const DEFAULT_STYLE = { icon: "\u2691", colorClass: "text-neutral-400 border-white/10" };

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
    <div className="glass rounded-2xl p-4 h-full flex flex-col">
      <h2 className="text-xs font-bold uppercase tracking-widest text-neutral-400 mb-3">
        Commentary
      </h2>

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
                    <span className="text-base leading-none mt-0.5 shrink-0" aria-hidden="true">
                      {style.icon}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm leading-snug">{entry.text}</p>
                      <span className="text-xs opacity-50 font-mono mt-1 block">
                        {formatTime(entry.timestamp)}
                      </span>
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
