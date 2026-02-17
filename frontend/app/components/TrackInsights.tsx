"use client";

interface LapRecord {
  time: string;
  driver: string;
  year: number;
}

interface CircuitInfo {
  circuit_name: string;
  track_length_km: number;
  laps: number;
  lap_record: LapRecord;
  first_gp: number;
  circuit_type: string;
}

interface TrackInsightsProps {
  circuit: CircuitInfo | null;
}

export default function TrackInsights({ circuit }: TrackInsightsProps) {
  if (!circuit) return null;

  const totalDist = (circuit.laps * circuit.track_length_km).toFixed(1);

  return (
    <div className="glass rounded-xl p-4 space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="text-sm font-black italic text-white leading-tight">
          {circuit.circuit_name}
        </h4>
        <span className="text-[10px] font-bold uppercase tracking-widest text-neutral-500 shrink-0">
          {circuit.circuit_type}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-neutral-400">
        <span>
          <b className="text-white">{circuit.track_length_km} km</b> × {circuit.laps} laps = {totalDist} km
        </span>
        <span>
          Record: <b className="text-white font-mono">{circuit.lap_record.time}</b>
          {circuit.lap_record.driver !== "-" && (
            <> ({circuit.lap_record.driver}, {circuit.lap_record.year})</>
          )}
        </span>
        <span>
          Since <b className="text-white">{circuit.first_gp}</b>
        </span>
      </div>
    </div>
  );
}
