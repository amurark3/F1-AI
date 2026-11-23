"use client";

import { StateTag } from "@/app/race-control/grand-prix/StateTag";
import { DriverName } from "@/app/ui/names/DriverName";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { RadioClip, type ClipState } from "./RadioClip";
import { clipCount, lapGroups, MOMENT_TAG, moreSummary, RACE_TITLE, radioTitle, timesNote } from "./radioModel";
import { useRadioPlayer, type RadioPlayer } from "./useRadioPlayer";

import type { DebriefRadio, RadioClip as Clip, RadioMoment } from "./debriefTypes";

const CARD = "rounded-md border border-rc-line bg-(--surface) p-5 sm:p-6";
const ROW =
  "grid grid-cols-[52px_minmax(0,1fr)] gap-2 border-b border-rc-line-soft py-3 sm:grid-cols-[76px_minmax(0,1fr)] sm:gap-3";
const LAP = "font-mono text-[11px] font-semibold leading-[2] text-rc-ink-3";
const NOTE = "mt-3.5 font-mono text-[10px] font-medium uppercase leading-[1.6] tracking-[0.1em] text-rc-ink-3";

function MomentTitle({ moment }: { moment: RadioMoment }) {
  const { driver, detail } = moment;
  if (!driver) return <>{RACE_TITLE[moment.kind]}</>;
  const name = <DriverName name={driver.driver_name} code={driver.driver_code} />;
  if (moment.kind === "incident") return <>{detail}</>;
  if (moment.kind === "retirement") return <>{name} retires</>;
  return (
    <>
      {name}
      {moment.kind === "stop" ? " stops" : ""} · {detail}
    </>
  );
}

function stateOf(player: RadioPlayer, clip: Clip): ClipState {
  if (player.failed.has(clip.url)) return "failed";
  if (player.now.url !== clip.url) return "idle";
  return player.now.playing ? "playing" : "paused";
}

function Clips({
  clips,
  offset,
  player,
  flush,
}: {
  clips: Clip[];
  offset: number | null;
  player: RadioPlayer;
  flush?: boolean;
}) {
  return (
    <div className={`${flush ? "" : "mt-2 "}flex flex-wrap gap-2`}>
      {clips.map((clip) => {
        const active = player.now.url === clip.url;
        return (
          <RadioClip
            key={clip.url}
            clip={clip}
            offset={offset}
            state={stateOf(player, clip)}
            elapsed={active ? player.now.elapsed : 0}
            duration={active ? player.now.duration : null}
            onToggle={player.toggle}
          />
        );
      })}
    </div>
  );
}

/** The race's team-radio clips, each with the moment it came within a lap of; one plays at a time. */
export function RadioMoments({ radio }: { radio: DebriefRadio }) {
  const player = useRadioPlayer();
  const offset = radio.utc_offset_minutes;
  if (!radio.available) {
    return (
      <div className={CARD}>
        <PanelHeading eyebrow="Team radio · audio, no transcript" />
        <p className="text-sm text-rc-ink-3">{radio.reason}</p>
      </div>
    );
  }
  return (
    <div>
      <div className={CARD}>
        <PanelHeading
          eyebrow="Team radio · audio, no transcript"
          title={radioTitle(radio)}
          sub="Each clip sits with the stop, penalty, retirement or flag it came within a lap of · play to listen"
        />
        <div className="mt-2">
          {radio.moments.map((moment) => (
            <div key={`${moment.kind}-${moment.at}-${moment.driver?.driver_code ?? ""}`} className={ROW}>
              <span className={LAP}>L{moment.lap}</span>
              <div>
                <p className="flex flex-wrap items-center gap-2.5">
                  <StateTag>{MOMENT_TAG[moment.kind]}</StateTag>
                  <b className="font-semibold text-rc-ink">
                    <MomentTitle moment={moment} />
                  </b>
                  <span className="font-mono text-[11px] font-medium text-rc-ink-3">
                    {clipCount(moment.clips.length)}
                  </span>
                </p>
                <Clips clips={moment.clips} offset={offset} player={player} />
              </div>
            </div>
          ))}
        </div>
        {radio.unattached.length > 0 && (
          <details className="mt-3.5">
            <summary className="cursor-pointer py-2 font-mono text-[11px] font-semibold uppercase tracking-[0.06em] text-rc-ink-2">
              {moreSummary(radio.unattached.length)}
            </summary>
            {lapGroups(radio.unattached).map((group) => (
              <div key={group.lap} className={ROW}>
                <span className={LAP}>L{group.lap}</span>
                <Clips clips={group.clips} offset={offset} player={player} flush />
              </div>
            ))}
          </details>
        )}
      </div>
      <p className={NOTE}>
        Clips: OpenF1 team_radio (audio file, no transcript), played from F1&apos;s archive · moments: OpenF1 pit and
        race control, retirements from the classification · red-flag pit-lane entries are not stops ·{" "}
        {timesNote(offset)}
      </p>
    </div>
  );
}
