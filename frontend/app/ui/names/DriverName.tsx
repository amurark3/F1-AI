"use client";

import { directorySeason, useSeasonDirectory } from "@/app/race-control/profiles/EntityLinks";

import { driverCode, driverLabel, driverSurname, type DriverIdentity, type DriverNameVariant } from "./names";

export interface DriverNameProps extends DriverIdentity {
  /** `full` in heroes (default), `codeLast` in tables, `code` on chart axes, `last` where space is short. */
  variant?: DriverNameVariant;
  className?: string;
}

function lacks(text: string | null | undefined): boolean {
  return !text?.trim();
}

/** Whether the variant needs a part the payload did not send, and this season's directory could have it. */
function readsDirectory(identity: DriverIdentity, variant: DriverNameVariant): boolean {
  const thisSeason = identity.year === undefined || identity.year === null || identity.year === directorySeason();
  if (!thisSeason) return false;
  if (variant === "last") return lacks(identity.lastName);
  if (variant === "code") return lacks(identity.code);
  return variant === "codeLast" && (lacks(identity.lastName) || lacks(identity.code));
}

/**
 * A driver's name by the plan's rule, read from data (see `names.ts`): the
 * payload's surname or code, else this season's directory, else the full name.
 * A shortened name carries the full one as its tooltip.
 */
export function DriverName({ variant = "full", className, ...identity }: DriverNameProps) {
  const directory = useSeasonDirectory(readsDirectory(identity, variant));
  const title = (shown: string) => (shown === identity.name ? undefined : identity.name);

  if (variant !== "codeLast") {
    const text = driverLabel(identity, variant, directory);
    return (
      <span className={className} title={title(text)}>
        {text}
      </span>
    );
  }
  const last = driverSurname(identity, directory) ?? identity.name;
  const code = driverCode(identity, directory);
  return (
    <span
      className={`inline-flex items-baseline gap-2 ${className ?? ""}`}
      title={title(driverLabel(identity, variant, directory))}
    >
      <span>{last}</span>
      {code && <span className="font-mono text-[11px] font-medium text-rc-ink-3">{code}</span>}
    </span>
  );
}
