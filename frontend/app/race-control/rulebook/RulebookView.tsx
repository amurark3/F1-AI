"use client";

import { useState, type FormEvent } from "react";
import useSWRMutation from "swr/mutation";

import { API_BASE } from "@/app/constants/api";
import { PageHero } from "@/app/ui/PageHero";
import { Section } from "@/app/ui/section/Section";
import { describeFailure } from "@/app/ui/section/sectionState";

import { RulebookAnswer } from "./RulebookAnswer";
import { QUICK_QUESTIONS, answerState, type RulebookResult } from "./rulebookModel";

const SEARCH_URL = `${API_BASE}/api/race-control/rulebook/search`;

async function search(url: string, { arg }: { arg: { query: string } }): Promise<RulebookResult> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(arg),
  });
  if (!res.ok) throw new Error(`The rulebook search failed (HTTP ${res.status}).`);
  return (await res.json()) as RulebookResult;
}

export function RulebookView() {
  const [query, setQuery] = useState("");
  const [asked, setAsked] = useState<string | null>(null);
  const { trigger, data, error, isMutating } = useSWRMutation<RulebookResult, Error, string, { query: string }>(
    SEARCH_URL,
    search,
  );

  const ask = (question: string) => {
    setAsked(question);
    void trigger({ query: question }, { throwOnError: false });
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (trimmed !== "") ask(trimmed);
  };
  const state = {
    ...answerState(isMutating, error, data, (failure) => describeFailure(failure, false)),
    refreshing: isMutating,
  };

  return (
    <div>
      <PageHero eyebrow="Rulebook · FIA Formula One Regulations and stewards' decisions" title="Ask the rulebook" />
      <form role="search" aria-label="Ask the rulebook" onSubmit={submit} className="mt-6 flex gap-2.5">
        <input
          type="text"
          aria-label="Question"
          maxLength={300}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="h-14 min-w-0 flex-1 rounded-md border border-rc-line bg-(--surface) px-[18px] text-[17px] text-rc-ink"
        />
        <button
          type="submit"
          className="inline-flex h-14 shrink-0 items-center bg-f1-red px-6 font-display text-[19px] font-extrabold uppercase leading-none tracking-[0.02em] text-rc-ink transition-[filter] hover:brightness-110"
        >
          Search
        </button>
      </form>
      <ul aria-label="Quick questions" className="mt-3.5 flex flex-wrap gap-2">
        {QUICK_QUESTIONS.map((question) => (
          <li key={question}>
            <button
              type="button"
              onClick={() => {
                setQuery(question);
                ask(question);
              }}
              className="rounded-full border border-rc-line px-3.5 py-2 text-[13px] text-rc-ink-2 transition-colors hover:border-rc-ink-3 hover:text-rc-ink"
            >
              {question}
            </button>
          </li>
        ))}
      </ul>
      {asked !== null && (
        <Section state={{ ...state, retry: () => ask(asked) }} label="Answer" skeletonClassName="h-72" className="mt-7">
          {data && data.status !== "unavailable" && (
            <RulebookAnswer answer={data} retry={() => ask(asked)} refreshing={isMutating} />
          )}
        </Section>
      )}
    </div>
  );
}
