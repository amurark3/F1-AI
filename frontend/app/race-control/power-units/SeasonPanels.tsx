/**
 * The car page's supporting panels: where every number on the screen came from.
 *
 * Server-safe: no state, no effects.
 */
import { ExternalLink, FileWarning, FileX2 } from "lucide-react";

import { InlineNotice } from "../components/RaceControlPrimitives";

import type { PowerUnitsResponse, WithdrawnDocument } from "./powerUnitsModel";

export function FiaLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.14em] text-[#9EC5FF] hover:text-white"
    >
      {label}
      <ExternalLink className="h-3 w-3" aria-hidden="true" />
      <span className="sr-only">(opens the FIA document)</span>
    </a>
  );
}

function WithdrawnList({ items }: { items: WithdrawnDocument[] }) {
  return (
    <InlineNotice title={`${items.length} FIA document(s) withdrawn or replaced — not counted`} tone="info">
      <ul className="mt-1 space-y-1">
        {items.map((item) => (
          <li key={`${item.url}-${item.reason}`} className="flex flex-wrap items-center gap-2">
            <FileX2 className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span className="line-through decoration-[#5A6273]">{item.title}</span>
            <span className="text-[#8E96A8]">— {item.reason}</span>
            <FiaLink href={item.url} label="Open" />
          </li>
        ))}
      </ul>
    </InlineNotice>
  );
}

/** Where every number came from, and what the collection could not read. */
export function Provenance({ data }: { data: PowerUnitsResponse }) {
  return (
    <div className="flex flex-col gap-3">
      {data.unread.length > 0 && (
        <InlineNotice title={`${data.unread.length} FIA document(s) could not be read`} tone="warning">
          <ul className="mt-1 space-y-1">
            {data.unread.map((item) => (
              <li key={item.url} className="flex flex-wrap items-center gap-2">
                <FileWarning className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span>
                  {item.event}: {item.title} — {item.reason}
                </span>
                <FiaLink href={item.url} label="Open" />
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs">Counts that depend on these documents may be incomplete until they are read.</p>
        </InlineNotice>
      )}
      {(data.withdrawn ?? []).length > 0 && <WithdrawnList items={data.withdrawn ?? []} />}
      {data.warnings.length > 0 && (
        <InlineNotice title="Checks that did not add up" tone="warning">
          <ul className="list-disc space-y-1 pl-4">
            {data.warnings.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </InlineNotice>
      )}
      <InlineNotice title="Where these numbers come from">
        <ul className="list-disc space-y-1 pl-4">
          {(data.notes ?? []).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </InlineNotice>
    </div>
  );
}
