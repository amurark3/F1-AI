"use client";

import { BrandMark } from "@/app/ui/BrandLockup";

import { AnswerMarkdown } from "./AnswerMarkdown";
import { answerHeader, type Message } from "./engineerModel";
import { ReachChart } from "./ReachChart";

const HEADER =
  "mb-2.5 flex items-center gap-2.5 font-mono text-[11px] font-semibold uppercase leading-snug tracking-[0.14em] text-rc-ink-3";

/** The line over an answer: the B1 mark, "Engineer", and what the answer read. */
export function AnswerHeader({ text, live = false }: { text: string; live?: boolean }) {
  return (
    <p className={HEADER} aria-live={live ? "polite" : undefined}>
      <BrandMark className="size-[22px] shrink-0" />
      {text}
    </p>
  );
}

/** The source chips of an answer or of the starter prompts: what the data was read from. */
export function SourceChips({ sources, className = "" }: { sources: readonly string[]; className?: string }) {
  if (sources.length === 0) return null;
  return (
    <ul aria-label="Sources" className={`flex flex-wrap gap-1.5 ${className}`}>
      {sources.map((chip) => (
        <li
          key={chip}
          className="rounded-[3px] border border-rc-line px-2 py-1.5 font-mono text-[10px] font-medium leading-none tracking-[0.06em] text-rc-ink-3"
        >
          {chip}
        </li>
      ))}
    </ul>
  );
}

interface EngineerAnswerProps {
  message: Message;
  /** Given only to the latest answer: asks the same question again. */
  onRegenerate?: () => void;
}

export function EngineerAnswer({ message, onRegenerate }: EngineerAnswerProps) {
  const { content, data } = message;
  return (
    <article className="max-w-full motion-safe:animate-fade-up md:max-w-[86%]">
      <AnswerHeader text={answerHeader(data?.subject)} />
      <AnswerMarkdown content={content} />
      {data?.charts.map((chart) => (
        <ReachChart key={chart.title} chart={chart} />
      ))}
      <SourceChips sources={data?.sources ?? []} className="mt-1.5" />
      {onRegenerate && (
        <p className="mt-3">
          <button
            type="button"
            onClick={onRegenerate}
            className="font-mono text-[10px] font-medium uppercase leading-none tracking-[0.1em] text-rc-ink-2 underline decoration-rc-line underline-offset-[3px] hover:text-rc-ink"
          >
            Regenerate
          </button>
        </p>
      )}
    </article>
  );
}
