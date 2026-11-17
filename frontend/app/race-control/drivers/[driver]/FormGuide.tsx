import { EYEBROW } from "@/app/ui/typography";

import type { FormChip, FormTone } from "./driverModel";

const CHIP =
  "grid h-14 w-[52px] place-items-center rounded border font-display text-[22px] font-extrabold leading-none";

const TONE: Record<FormTone, string> = {
  win: "border-rc-gold bg-rc-gold text-background",
  podium: "border-rc-gold/50 text-rc-ink",
  plain: "border-rc-line text-rc-ink",
  out: "border-rc-red-text/50 text-rc-red-text",
};

/** The last five races as chips: the place, or the code of a car that did not finish, over the round. */
export function FormGuide({ chips }: { chips: readonly FormChip[] }) {
  return (
    <div>
      <p className={EYEBROW}>Last five</p>
      <ol aria-label="Last five races" className="mt-3 flex gap-1.5">
        {chips.map((chip) => (
          <li key={chip.axis} title={chip.sentence} className={`${CHIP} ${TONE[chip.tone]}`}>
            <span aria-hidden="true" className="flex flex-col items-center gap-1.5">
              {chip.text}
              <em
                className={`font-mono text-[9px] font-medium not-italic leading-none ${chip.tone === "win" ? "text-background" : "text-rc-ink-3"}`}
              >
                {chip.axis}
              </em>
            </span>
            <span className="sr-only">{chip.sentence}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
