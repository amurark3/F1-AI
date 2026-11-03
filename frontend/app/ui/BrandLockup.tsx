import { f1, rc } from "./tokens";

/**
 * Geometry of the B1 "Apex" mark: a racing line through a corner, apex in red.
 * Identical to `app/icon.svg`, the tab icon; `BrandLockup.test.tsx` compares
 * the two, so change both together.
 */
const MARK = {
  viewBox: "0 0 64 64",
  size: 64,
  tileRadius: 14,
  line: "M15 52C15 31 25 17 50 14",
  lineWidth: 7.5,
  apex: { cx: 30, cy: 35, r: 6 },
} as const;

/**
 * The F1·AI header lockup: the B1 mark beside the wordmark.
 *
 * The wordmark follows the mockups' `.logo` (`docs/design/redesign/system.css`):
 * the display face at 800, with a small red square between "F1" and "AI".
 * It reads to assistive tech as one image named "F1 AI".
 */
export default function BrandLockup() {
  return (
    <span role="img" aria-label="F1 AI" className="inline-flex shrink-0 items-center gap-2.5">
      <svg viewBox={MARK.viewBox} aria-hidden="true" focusable="false" className="size-7 shrink-0">
        <rect width={MARK.size} height={MARK.size} rx={MARK.tileRadius} fill={rc.hero} />
        <path d={MARK.line} fill="none" stroke={rc.ink} strokeWidth={MARK.lineWidth} strokeLinecap="round" />
        <circle cx={MARK.apex.cx} cy={MARK.apex.cy} r={MARK.apex.r} fill={f1.red} />
      </svg>
      <span className="flex items-center font-display text-[26px] font-extrabold leading-none tracking-[0.01em] text-rc-ink">
        F1
        <span className="mx-[3px] inline-block size-1.5 translate-y-px bg-f1-red" />
        AI
      </span>
    </span>
  );
}
