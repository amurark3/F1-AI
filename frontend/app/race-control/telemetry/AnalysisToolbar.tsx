"use client";

import { Segmented } from "@/app/ui/Segmented";

import { TABS, type TabKey, type WeekendSession } from "./telemetryModel";

import type { ReactNode } from "react";

/** The id of the panel the view switch controls. */
export const ANALYSIS_PANEL_ID = "telemetry-analysis";

export interface AnalysisToolbarProps {
  tab: TabKey;
  onTab: (tab: TabKey) => void;
  /** Null until the weekend's sessions are known. */
  sessions: WeekendSession[] | null;
  session: string | null;
  /** Whether the current view can show a session; the rest are left out. */
  allowed: (code: string) => boolean;
  onSession: (code: string) => void;
  /** The current view's own pickers (driver, lap, and later the qualifying part), after the session. */
  children?: ReactNode;
}

/**
 * The one toolbar under the race picker: the view switch, then the session,
 * then whatever the view itself picks. It wraps rather than scrolls.
 */
export function AnalysisToolbar({ tab, onTab, sessions, session, allowed, onSession, children }: AnalysisToolbarProps) {
  const offered = sessions?.filter((item) => allowed(item.code)) ?? [];
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-rc-line pb-4">
      <Segmented
        label="Analysis"
        semantics="tablist"
        controls={ANALYSIS_PANEL_ID}
        value={tab}
        onChange={onTab}
        options={TABS.map((item) => ({ value: item.key, label: item.label }))}
      />
      {sessions !== null && offered.length === 0 && (
        <p className="font-mono text-xs text-rc-ink-3">No session of this kind on this weekend.</p>
      )}
      {offered.length > 0 && (
        <Segmented
          label="Session"
          value={session ?? ""}
          onChange={onSession}
          options={offered.map((item) => ({ value: item.code, label: item.name, disabled: !item.started }))}
        />
      )}
      {children}
    </div>
  );
}
