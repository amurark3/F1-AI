"use client";

import { Fragment } from "react";

import { Section } from "@/app/ui/section/Section";

import { NoteList } from "../PowerUnitsParts";

import { allocationGroups, carNotes, sourceLine } from "./carModel";
import { useCar, type CarSectionProps } from "./useCar";

/** Where the figures come from, how fresh they are, and what the collection could not read. */
export function CarSourceNote(props: CarSectionProps) {
  const { state, data, car } = useCar(props);
  const groups = allocationGroups(data?.elements ?? []);
  return (
    <Section state={state} label="Source note" skeletonClassName="h-16">
      {data && car && (
        <footer className="mt-7 grid gap-1.5 font-mono text-[10px] uppercase leading-[1.6] tracking-[0.1em] text-rc-ink-3">
          <p>{sourceLine(data.freshness)}</p>
          {groups.length > 0 && (
            <p>
              Allocations as the FIA states them:{" "}
              {groups.map((group, index) => (
                <Fragment key={group.codes}>
                  {index > 0 && " · "}
                  {group.codes}
                  {group.doc !== null && (
                    <>
                      {" ("}
                      {group.url ? (
                        <a
                          href={group.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="underline decoration-rc-line underline-offset-[3px] hover:text-rc-ink"
                        >
                          {group.doc} ↗
                        </a>
                      ) : (
                        group.doc
                      )}
                      )
                    </>
                  )}
                </Fragment>
              ))}
            </p>
          )}
          <NoteList notes={carNotes(data, car)} />
        </footer>
      )}
    </Section>
  );
}
