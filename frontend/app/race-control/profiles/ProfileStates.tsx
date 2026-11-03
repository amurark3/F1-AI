/**
 * Loading and missing states shared by the team and driver pages.
 *
 * Server-safe apart from the retry callback, which the caller owns.
 */
import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { InlineNotice, PageLoader, Panel } from "../components/RaceControlPrimitives";

export function ProfileLoading({ what }: { what: string }) {
  return (
    <PageLoader title={`Loading ${what}`} detail="Reading the season's results, standings and power-unit usage." />
  );
}

export function ProfileNotFound({ what, backHref, backLabel }: { what: string; backHref: string; backLabel: string }) {
  return (
    <Panel className="p-8">
      <p className="text-neutral-300">No {what} by that name raced this season.</p>
      <Link
        href={backHref}
        className="mt-5 inline-flex items-center gap-2 rounded-lg border border-[#00FF78]/35 bg-[#00FF78]/10 px-4 py-2.5 text-sm font-black uppercase tracking-wider text-[#00FF78] transition-colors hover:bg-[#00FF78] hover:text-black"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        {backLabel}
      </Link>
    </Panel>
  );
}

export function ProfileUnavailable({ onRetry, errorId }: { onRetry: () => void; errorId?: string }) {
  return (
    <InlineNotice title="Profile unavailable" tone="error">
      This season&apos;s results could not be loaded.
      {errorId && <span className="ml-1 font-mono text-xs text-neutral-400">(ref {errorId})</span>}
      <button type="button" onClick={onRetry} className="ml-2 font-bold text-white underline decoration-white/30">
        Retry
      </button>
    </InlineNotice>
  );
}
