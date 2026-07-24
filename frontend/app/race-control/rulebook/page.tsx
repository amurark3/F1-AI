"use client";

import { BookOpenCheck } from "lucide-react";
import { useState } from "react";
import useSWRMutation from "swr/mutation";

import { API_BASE } from "@/app/constants/api";

import { InlineNotice, Panel, SectionHeader, SectionLoader, StatusPill, WorkspaceSplit, rcFont } from "../components/RaceControlPrimitives";

interface SearchArgs {
  query: string;
  category: string;
}

interface RulebookResult {
  query: string;
  category: string;
  source: "chroma-rag" | "fallback";
  error?: string | null;
  answer: string;
  citations: Array<{ document: string; year: string; category?: string; page?: string | null; snippet: string }>;
}

async function searchRulebook(url: string, { arg }: { arg: SearchArgs }) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(arg),
  });
  if (!res.ok) throw new Error(`Rulebook search failed: ${res.status}`);
  return res.json() as Promise<RulebookResult>;
}

const QUICK_QUESTIONS = [
  "What can we change under parc ferme?",
  "What makes a pit release unsafe?",
  "How should we think about cost cap operational constraints?",
  "What 2026 technical changes affect strategy?",
];

/** Badge label for the answer source: fallback, live citation, or idle. */
function sourceStatusLabel(result: RulebookResult | undefined): string {
  if (result?.source === "fallback") return "Limited";
  return result ? "Cited" : "Ready";
}

export default function RulebookPage() {
  const [query, setQuery] = useState("What can we change under parc ferme?");
  const [category, setCategory] = useState("Sporting");
  const { trigger, data, error, isMutating } = useSWRMutation<
    RulebookResult,
    Error,
    string,
    SearchArgs
  >(`${API_BASE}/api/race-control/rulebook/search`, searchRulebook);
  const runSearch = () => trigger({ query, category });

  return (
    <div>
      <SectionHeader
        eyebrow="Visual Regulations Assistant"
        title="Rulebook Desk"
        description="Turn FIA sporting, technical, and financial regulation questions into operational constraints with cited snippets."
      />

      <Panel className="mb-7 p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-start gap-3">
            <BookOpenCheck className="mt-1 h-5 w-5 shrink-0 text-[#00FF78]" />
            <div>
              <p className="text-xs font-black uppercase tracking-[0.16em] text-neutral-400" style={rcFont}>Regulation Sources</p>
              <h2 className="mt-1 text-2xl font-black text-white" style={rcFont}>FIA PDFs, cited answers, operational constraints</h2>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusPill>2024-2026 corpus</StatusPill>
            <StatusPill color="#3671C6">Source snippets</StatusPill>
          </div>
        </div>
      </Panel>

      <WorkspaceSplit className="xl:[&>*:first-child]:basis-[42%] xl:[&>*:last-child]:flex-1">
        <Panel className="p-5">
          <h2 className="text-xl font-black italic uppercase text-white mb-5" style={rcFont}>Search Regulations</h2>
          <label className="block mb-4">
            <span className="block text-xs font-black uppercase tracking-[0.18em] text-neutral-300 mb-2">Category</span>
            <select value={category} onChange={(e) => setCategory(e.target.value)} className="h-12 w-full rounded-lg bg-[#151817] border border-white/12 px-3 text-base text-white outline-none focus:border-[#00FF78]/70">
              {["Sporting", "Technical", "Financial", "All"].map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>
          <label className="block mb-4">
            <span className="block text-xs font-black uppercase tracking-[0.18em] text-neutral-300 mb-2">Question</span>
            <textarea value={query} onChange={(e) => setQuery(e.target.value)} rows={5} className="w-full rounded-lg bg-[#151817] border border-white/12 px-3 py-3 text-base text-white outline-none resize-none focus:border-[#00FF78]/70" />
          </label>
          <button onClick={() => void runSearch()} disabled={isMutating || !query.trim()} className="w-full rounded-lg bg-[#00FF78] px-4 py-3 text-sm font-black uppercase tracking-wider text-black disabled:opacity-50">
            {isMutating ? "Searching..." : "Search rulebook"}
          </button>

          <div className="mt-5">
            <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400 mb-3">Fast questions</p>
            <div className="space-y-2">
              {QUICK_QUESTIONS.map((item) => (
                <button key={item} onClick={() => setQuery(item)} className="w-full text-left rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2.5 text-sm text-neutral-300 hover:text-white">
                  {item}
                </button>
              ))}
            </div>
          </div>
        </Panel>

        {isMutating ? (
          <SectionLoader
            title="Searching regulation index"
            detail="Looking for cited FIA snippets and translating them into an operational answer."
          />
        ) : (
        <Panel className="p-5" accent="#00FF78">
          <div className="flex items-start justify-between gap-3 mb-5">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400 mb-2" style={rcFont}>Operational Answer</p>
              <h2 className="text-2xl font-black italic uppercase text-white leading-none" style={rcFont}>{data?.category ?? category} Regulations</h2>
            </div>
            <StatusPill color={data?.source === "fallback" ? "#FFF200" : "#00FF78"}>{sourceStatusLabel(data)}</StatusPill>
          </div>
          {error && (
            <div className="mb-5">
              <InlineNotice title="Rulebook Search Unavailable" tone="error">
                The regulation search did not return a result.
                <button onClick={() => void runSearch()} className="ml-2 font-bold text-white underline decoration-white/30">Retry</button>
              </InlineNotice>
            </div>
          )}
          {data?.error && (
            <div className="mb-5">
              <InlineNotice title="Citation Search Limited" tone="warning">
                The regulation index could not return cited excerpts for this search. The answer below is a general operations note.
              </InlineNotice>
            </div>
          )}
          <p className="text-base text-neutral-300 leading-relaxed mb-6">
            {data?.answer ?? "Search a regulation topic to see the operational answer and source snippets."}
          </p>

          <h3 className="text-sm font-black uppercase tracking-wider text-neutral-400 mb-3">Citations</h3>
          <div className="space-y-3">
            {(data?.citations ?? []).map((citation, index) => (
              <div key={`${citation.document}-${index}`} className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
                <div className="flex items-center gap-2 mb-2">
                  <StatusPill color="#3671C6">{citation.year}</StatusPill>
                  {citation.category && <StatusPill color="#FF8000">{citation.category}</StatusPill>}
                  {citation.page && <StatusPill color="#BE3AFF">Page {citation.page}</StatusPill>}
                </div>
                <p className="mb-2 text-sm font-bold text-white">{citation.document}</p>
                <p className="text-sm text-neutral-400 leading-relaxed">{citation.snippet}</p>
              </div>
            ))}
            {data?.citations.length === 0 && (
              <InlineNotice title="No Citations" tone="warning">
                Try broadening the category filter or using a shorter regulation topic.
              </InlineNotice>
            )}
          </div>
        </Panel>
        )}
      </WorkspaceSplit>
    </div>
  );
}
