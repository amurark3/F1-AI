"use client";

import { API_BASE } from "@/app/constants/api";
import type { OverviewShell } from "@/app/race-control/components/CommandCenterPanels";
import { useSection } from "@/app/ui/section/useSection";
import { EYEBROW } from "@/app/ui/typography";

import { AnswerHeader, SourceChips } from "./EngineerAnswer";
import { starterPrompts } from "./engineerModel";

/** The top bar's race chip reads this same segment with the same settings, so one request serves both. */
const SHELL_SWR = { revalidateOnFocus: false, dedupingInterval: 120_000 };

interface StarterPromptsProps {
  isLoading: boolean;
  onAsk: (text: string) => void;
}

/**
 * The empty thread: what the engineer answers from, and questions computed
 * from the same shell segment the top bar reads. While it is pending or has
 * failed, only the rules question shows: the prompts are a convenience.
 */
export function StarterPrompts({ isLoading, onAsk }: StarterPromptsProps) {
  const year = new Date().getFullYear();
  const { data } = useSection<OverviewShell>(`${API_BASE}/api/race-control/overview/${year}/shell`, {
    config: SHELL_SWR,
  });
  const { prompts, sources } = starterPrompts(data);

  return (
    <article className="max-w-full md:max-w-[86%]">
      <AnswerHeader text="Engineer" />
      <p className="text-sm leading-[1.65] text-rc-ink-2">
        Ask about any race, driver, rule or prediction. Answers are read from the same data as the screens, and list the
        sources they used.
      </p>
      <p className={`${EYEBROW} mt-[22px]`}>Start with</p>
      <ul className="mt-3.5 grid gap-2.5 md:grid-cols-2">
        {prompts.map(({ kicker, text }) => (
          <li key={text}>
            <button
              type="button"
              disabled={isLoading}
              onClick={() => onAsk(text)}
              className="flex h-full w-full flex-col gap-[9px] rounded-md border border-rc-line bg-(--surface) px-4 py-3.5 text-left transition-colors hover:border-rc-ink-3 disabled:opacity-50"
            >
              <span className="font-mono text-[10px] font-semibold uppercase leading-none tracking-[0.16em] text-rc-ink-3">
                {kicker}
              </span>
              <span className="text-sm leading-[1.45] text-rc-ink">{text}</span>
            </button>
          </li>
        ))}
      </ul>
      <SourceChips sources={sources} className="mt-3" />
    </article>
  );
}
