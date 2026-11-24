"use client";

import { EYEBROW } from "../typography";

import { chooseAnalytics, useConsentPrompt } from "./analyticsConsent";

/** Allow and Decline weigh the same: refusing is as easy as agreeing. */
const CHOICE =
  "h-9 flex-1 rounded border border-rc-ink/35 font-mono text-[11px] font-semibold uppercase leading-none tracking-[0.18em] text-rc-ink transition-colors hover:border-rc-ink";

/**
 * The analytics cookie question: a raised
 * card pinned to the bottom corner that never blocks the page. It sits after the
 * footer in the DOM, so the footer's "Cookie settings" tabs straight into it.
 */
export function ConsentBanner() {
  const open = useConsentPrompt();
  if (!open) return null;

  return (
    <section
      aria-labelledby="consent-title"
      className="fixed inset-x-5 bottom-4 z-40 rounded-md border border-rc-line bg-rc-raised px-5 pb-4 pt-[18px] shadow-lg motion-safe:animate-fade-up sm:right-auto sm:bottom-6 sm:w-[400px] lg:left-8"
    >
      <h2 id="consent-title" className={EYEBROW}>
        Analytics cookies
      </h2>
      <p className="mt-2.5 text-sm leading-relaxed text-rc-ink-2">
        May we use Google Analytics to see which pages people read? It sets cookies in your browser. Nothing is used for
        ads, and the site works the same if you decline.
      </p>
      <div className="mt-4 flex gap-2">
        <button type="button" className={CHOICE} onClick={() => chooseAnalytics("denied")}>
          Decline
        </button>
        <button type="button" className={CHOICE} onClick={() => chooseAnalytics("granted")}>
          Allow
        </button>
      </div>
      <p className="mt-2 text-xs text-rc-ink-3">Change this any time under Cookie settings in the footer.</p>
    </section>
  );
}
