"use client";

import { useId, useState } from "react";

import { LocalTimeZone } from "@/app/components/LocalTime";
import { API_BASE } from "@/app/constants/api";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { Section } from "@/app/ui/section/Section";
import { useSection } from "@/app/ui/section/useSection";

import { Panel } from "../components/RaceControlPrimitives";
import { StateTag } from "../grand-prix/StateTag";

import { feedRows, feedTitle, FIRST_FEED_SEASON, PREVIEW_ROWS, type WeekendFeed } from "./fiaFeedModel";
import { FiaFeedRow } from "./FiaFeedRow";

const LIVE_CONFIG = { refreshInterval: 120_000, revalidateOnFocus: false, dedupingInterval: 60_000 };
const PAST_CONFIG = { revalidateOnFocus: false, dedupingInterval: 120_000 };
const SUB = "Newest first, from the FIA's event documents";
const EMPTY = "border-t border-rc-line pt-7 pb-2 text-sm leading-relaxed text-rc-ink-3";

interface FeedRace {
  round: number;
  status: string;
}

function emptyCopy(feed: WeekendFeed): string {
  if (feed.event === null) {
    return "The FIA hasn't published a document for this weekend yet. Decisions show here once the scheduled check of fia.com picks them up.";
  }
  const others = feed.events.length;
  return `No stewards' decision, starting grid or deleted lap so far. ${others === 1 ? "1 other document is" : `${others} other documents are`} out.`;
}

function FeedBody({ feed, year, live }: { feed: WeekendFeed; year: number; live: boolean }) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const rows = feedRows(feed.events);
  const shown = open ? rows : rows.slice(0, PREVIEW_ROWS);
  return (
    <Panel as="section" className="p-5 sm:p-6">
      <PanelHeading
        as="h2"
        eyebrow="FIA decisions"
        title={feed.event === null ? "No documents yet" : feedTitle(rows)}
        sub={feed.event === null ? SUB : `${feed.event} · ${SUB}`}
        aside={live && <StateTag tone="red">Weekend live</StateTag>}
      />
      {rows.length === 0 ? (
        <p className={EMPTY}>{emptyCopy(feed)}</p>
      ) : (
        <>
          <ol id={listId} aria-label="FIA documents, newest first" className="border-t border-rc-line">
            {shown.map((event) => (
              <FiaFeedRow key={event.url} event={event} year={year} />
            ))}
          </ol>
          {rows.length > PREVIEW_ROWS && (
            <button
              type="button"
              aria-expanded={open}
              aria-controls={listId}
              onClick={() => setOpen((was) => !was)}
              className="mt-3.5 py-2 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-rc-ink hover:underline"
            >
              {open ? `Show the newest ${PREVIEW_ROWS}` : `Show all ${rows.length}`}
            </button>
          )}
          <p className="mt-4 font-mono text-[10px] uppercase leading-[1.6] tracking-[0.1em] text-rc-ink-3">
            {rows.length} of {feed.events.length} documents: stewards&rsquo; decisions, starting grids and deleted laps
            · red rule = changes a result or a grid slot
            {feed.latest !== null && ` · latest Doc ${feed.latest}`} · times in <LocalTimeZone /> · checked on a
            schedule that can run late, so fia.com may be ahead
          </p>
        </>
      )}
    </Panel>
  );
}

function FeedSection({ year, race }: { year: number; race: FeedRace }) {
  const live = race.status === "in_progress";
  const feed = useSection<WeekendFeed>(`${API_BASE}/api/weekend/${year}/${race.round}/feed`, {
    config: live ? LIVE_CONFIG : PAST_CONFIG,
  });
  return (
    <Section state={feed} label="FIA decisions" skeletonClassName="h-[360px]">
      {feed.data && <FeedBody feed={feed.data} year={year} live={live} />}
    </Section>
  );
}

/** The round's FIA stewards' decisions, starting grids and deleted laps, newest first, each linking to its PDF. */
export function FiaFeedPanel({ year, race }: { year: number; race: FeedRace | null | undefined }) {
  if (!race || race.status === "upcoming" || year < FIRST_FEED_SEASON) return null;
  return <FeedSection year={year} race={race} />;
}
