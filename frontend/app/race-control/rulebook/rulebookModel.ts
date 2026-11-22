import type { SectionStatus } from "@/app/ui/section/sectionState";

/** One quoted regulation passage. `codes` are the article numbers the passage names. */
export interface RulebookArticle {
  cite: number;
  codes: string[];
  source: string;
  document: string;
  page: number | null;
  excerpt: string;
}

/** One decided stewards' decision, with the FIA document it came from. */
export interface RulebookDecision {
  cite: number;
  number: number;
  event: string;
  title: string;
  car: number;
  driver: string | null;
  session: string | null;
  offence: string;
  decision: string;
  articles: string[];
  /** Article matches: the decision's articles that matched; keyword matches: the words it shares. */
  matched: string[];
  published: string;
  url: string;
}

export interface RulebookDecisions {
  match: "article" | "keyword";
  status: "matched" | "none" | "unavailable";
  events: number | null;
  total: number;
  articles: string[];
  words: string[];
  items: RulebookDecision[];
}

export interface RulebookSummary {
  heading: string;
  paragraph: string;
  written_by: "ai" | "computed";
  why: "ai_unavailable" | "check_failed" | null;
}

interface RulebookBase {
  query: string;
  year: number;
  /** Keyword: why the regulations were not searched; unavailable: why nothing was. */
  reason: string | null;
  articles: RulebookArticle[];
}

/** A search that found something to show: passages and decisions, or decisions alone. */
export interface RulebookSearched extends RulebookBase {
  status: "answered" | "keyword";
  decisions: RulebookDecisions;
  summary: RulebookSummary;
}

export interface RulebookUnavailable extends RulebookBase {
  status: "unavailable";
  decisions: null;
  summary: null;
}

export type RulebookResult = RulebookSearched | RulebookUnavailable;

export const QUICK_QUESTIONS = [
  "What is a power-unit grid penalty?",
  "When is a driver required to start from the pit lane?",
  "How do penalty points work?",
  "What counts as track limits?",
] as const;

export interface MarkupPart {
  kind: "text" | "bold" | "cite";
  value: string;
}

/** Splits the paragraph's `**bold**` spans and `[n]` source markers from the text around them. */
export function markupParts(text: string): MarkupPart[] {
  return text
    .split(/(\*\*[^*]+\*\*|\[\d+\])/)
    .filter((piece) => piece !== "")
    .map((piece): MarkupPart => {
      if (piece.startsWith("**")) return { kind: "bold", value: piece.slice(2, -2) };
      if (piece.startsWith("[")) return { kind: "cite", value: piece.slice(1, -1) };
      return { kind: "text", value: piece };
    });
}

const LISTED_CODES = 3;

/** "Article B3.5.3", "Articles B3.5.3 and B3.5.4", "Articles X, Y, Z and 2 more". */
export function articleLabel(codes: readonly string[]): string {
  if (codes.length === 0) return "";
  if (codes.length === 1) return `Article ${codes[0]}`;
  if (codes.length <= LISTED_CODES) return `Articles ${codes.slice(0, -1).join(", ")} and ${codes[codes.length - 1]}`;
  return `Articles ${codes.slice(0, LISTED_CODES).join(", ")} and ${codes.length - LISTED_CODES} more`;
}

/** The mono line above a passage: where it comes from. */
export function passageLabel(article: RulebookArticle, year: number): string {
  const codes = articleLabel(article.codes);
  const page = article.page ? ` · page ${article.page}` : "";
  const named = codes ? ` · ${codes}` : "";
  return `FIA ${year} F1 Regulations · ${article.source}${page}${named}`;
}

/** The mono line above a decision, up to its document link. */
export function decisionLead(decision: RulebookDecision, year: number): string {
  return `Stewards' decision · ${decision.event} ${year} · `;
}

/** The mono line above a decision, after its document link: what it matched on. */
export function decisionMatch(decision: RulebookDecision, match: "article" | "keyword"): string {
  return match === "article"
    ? ` · cites ${decision.matched.join(", ")}`
    : ` · keyword match: ${decision.matched.join(", ")}`;
}

/** The decision's own words, then who and where. */
export function decisionBody(decision: RulebookDecision): string {
  const driver = decision.driver ? `, ${decision.driver}` : "";
  const session = decision.session ? ` · ${decision.session}` : "";
  return `“${decision.decision}” Car ${decision.car}${driver}${session}: ${decision.offence}.`;
}

const LINKS = "Each decision links its FIA document";
const KEYWORD_BASIS = "Found by the question's words, not matched to an article of the regulations.";

/** Who wrote the text, in a sentence; empty when a keyword card's computed text needs no apology. */
function writtenBy(summary: RulebookSummary, basis: string): string {
  if (summary.written_by === "ai") {
    return `Written by AI from the ${basis} below only; every article, document and car number in it was checked against them.`;
  }
  if (summary.why === "check_failed") {
    return `The AI summary named something the ${basis} don't hold, so this text is computed from the ${basis} below instead.`;
  }
  if (summary.why === "ai_unavailable") {
    return `The AI summary is unavailable just now, so this text is computed from the ${basis} below.`;
  }
  return "";
}

function eyebrowFor(keyword: boolean, summary: RulebookSummary): string {
  if (keyword) return "Stewards' decisions · keyword matches";
  return summary.written_by === "ai" ? "Answer · AI-written" : "Answer · computed";
}

/** The eyebrow and the note under the sources, which say who wrote the text and what it rests on. */
export function answerCopy(result: RulebookSearched): { eyebrow: string; note: string } {
  const keyword = result.status === "keyword";
  const sentences = [writtenBy(result.summary, keyword ? "decisions" : "sources"), keyword ? KEYWORD_BASIS : ""];
  return {
    eyebrow: eyebrowFor(keyword, result.summary),
    note: [...sentences.filter((sentence) => sentence !== ""), LINKS].join(" "),
  };
}

/** The Answer section's status: a new question never shows the old answer. */
export function answerState(
  mutating: boolean,
  error: Error | undefined,
  data: RulebookResult | undefined,
  describe: (error: Error) => string,
): { status: SectionStatus; reason: string | null } {
  if (mutating) return { status: "pending", reason: null };
  if (error) return { status: "failed", reason: describe(error) };
  if (data?.status === "unavailable") return { status: "failed", reason: data.reason };
  return { status: "ready", reason: null };
}
