import Link from "next/link";

interface MissingProfileProps {
  year: number;
  /** "team" or "driver". */
  what: string;
  /** The f1db id the URL named. */
  id: string;
  backHref: string;
  backLabel: string;
}

/** What a team or driver URL shows when the season has nobody by that id. */
export function MissingProfile({ year, what, id, backHref, backLabel }: MissingProfileProps) {
  return (
    <div className="rounded-md border border-rc-line bg-(--surface) p-8">
      <p className="text-rc-ink-2">
        No {year} {what} with the id “{id}”.
      </p>
      <Link href={backHref} className="mt-4 inline-block text-rc-ink underline decoration-rc-dim underline-offset-2">
        {backLabel}
      </Link>
    </div>
  );
}
