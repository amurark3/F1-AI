import { Loader2, Timer, Trophy, Zap } from "lucide-react";

import PodiumDisplay, { type PodiumEntry } from "./PodiumDisplay";
import QualifyingResults, { type QualifyingEntry } from "./QualifyingResults";
import RaceResults, { type RaceResult } from "./RaceResults";

export interface CircuitInfo {
  circuit_name: string;
  track_length_km: number;
  laps: number;
  lap_record: { time: string; driver: string; year: number };
  first_gp: number;
  circuit_type: string;
}

export type ResultTab = "race" | "qualifying" | "sprint" | "sprint_quali";

/** Race detail payload returned by `/api/race/:year/:round`. */
export interface RaceDetail {
  circuit: CircuitInfo | null;
  podium: PodiumEntry[] | null;
  race_results: RaceResult[] | null;
  sprint_results: RaceResult[] | null;
  qualifying: Record<string, QualifyingEntry[]> | null;
  sprint_qualifying: Record<string, QualifyingEntry[]> | null;
  is_sprint?: boolean;
}

function ResultTabButton({
  tab,
  active,
  onSelect,
}: {
  tab: { key: ResultTab; label: string; icon: React.ReactNode };
  active: boolean;
  onSelect: (key: ResultTab) => void;
}) {
  return (
    <button
      onClick={() => onSelect(tab.key)}
      className={`flex items-center gap-1 px-3 py-1.5 text-[10px] font-black uppercase tracking-widest rounded-md transition-all duration-200 ${
        active ? "text-white" : "text-neutral-600 hover:text-neutral-400"
      }`}
      style={{
        background: active ? "#E10600" : "transparent",
        fontFamily: "var(--font-barlow, var(--font-geist-sans))",
      }}
    >
      {tab.icon}
      {tab.label}
    </button>
  );
}

function ResultTabsPanel({
  detail,
  resultTab,
  onSelectTab,
}: {
  detail: RaceDetail;
  resultTab: ResultTab;
  onSelectTab: (tab: ResultTab) => void;
}) {
  const tabs: Array<{ key: ResultTab; label: string; icon: React.ReactNode; show: boolean }> = [
    { key: "race", label: "Race", icon: <Trophy className="h-3 w-3" />, show: true },
    { key: "qualifying", label: "Quali", icon: <Timer className="h-3 w-3" />, show: true },
    { key: "sprint", label: "Sprint", icon: <Zap className="h-3 w-3" />, show: Boolean(detail.is_sprint) },
    { key: "sprint_quali", label: "SQ", icon: <Zap className="h-3 w-3" />, show: Boolean(detail.is_sprint) },
  ];

  return (
    <div className="space-y-3">
      <div className="flex gap-0.5 glass rounded-lg p-0.5 w-fit">
        {tabs
          .filter((t) => t.show)
          .map((t) => (
            <ResultTabButton key={t.key} tab={t} active={resultTab === t.key} onSelect={onSelectTab} />
          ))}
      </div>
      {resultTab === "race" && <RaceResults results={detail.race_results} />}
      {resultTab === "qualifying" && <QualifyingResults qualifying={detail.qualifying} />}
      {resultTab === "sprint" && <RaceResults results={detail.sprint_results} />}
      {resultTab === "sprint_quali" && <QualifyingResults qualifying={detail.sprint_qualifying} />}
    </div>
  );
}

export function CompletedRaceResults({
  detail,
  detailLoading,
  detailError,
  onRetry,
  resultTab,
  onSelectTab,
}: {
  detail?: RaceDetail;
  detailLoading: boolean;
  detailError: boolean;
  onRetry: () => void;
  resultTab: ResultTab;
  onSelectTab: (tab: ResultTab) => void;
}) {
  const showResults = detail && !detailLoading && (detail.race_results || detail.qualifying);

  return (
    <>
      {detailLoading && !detailError && (
        <div className="flex items-center gap-3 py-4">
          <Loader2 className="h-4 w-4 animate-spin" style={{ color: "#E10600" }} />
          <p className="text-xs text-neutral-500">Loading race data…</p>
        </div>
      )}
      {detailError && (
        <div className="py-4 text-center space-y-2">
          <p className="text-sm text-neutral-500">Failed to load race data.</p>
          <button
            onClick={onRetry}
            className="text-xs font-black uppercase tracking-widest px-4 py-2 rounded-lg text-white"
            style={{ background: "#E10600", fontFamily: "var(--font-barlow, var(--font-geist-sans))" }}
          >
            Retry
          </button>
        </div>
      )}
      {detail?.podium && (
        <div>
          <p
            className="text-[10px] font-black uppercase tracking-[0.18em] text-neutral-600 mb-3"
            style={{ fontFamily: "var(--font-barlow, var(--font-geist-sans))" }}
          >
            Podium
          </p>
          <PodiumDisplay podium={detail.podium} />
        </div>
      )}
      {showResults && detail && <ResultTabsPanel detail={detail} resultTab={resultTab} onSelectTab={onSelectTab} />}
    </>
  );
}
