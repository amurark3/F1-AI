import type { OverviewShell } from "@/app/race-control/components/CommandCenterPanels";
import type { TableStakes } from "@/app/race-control/weekend/weekendTypes";

/** One row of a reach chart: points today, and the most the row can still reach. */
export interface ReachRow {
  key: string;
  name: string;
  team: string;
  points: number;
  max: number;
}

/** The chart kind a standings tool draws (`ReachChart` in `backend/app/api/tools/provenance.py`). */
export interface ReachChartData {
  kind: "reach";
  title: string;
  championship: "drivers" | "constructors";
  year: number;
  rows: ReachRow[];
}

/** What an answer read, sent ahead of it as an `[ANSWER_DATA]` block. */
export interface AnswerData {
  subject: string | null;
  sources: string[];
  charts: ReachChartData[];
}

export interface Message {
  role: "user" | "assistant";
  content: string;
  data?: AnswerData;
}

export interface Chat {
  id: string;
  title: string;
  updatedAt: number;
  messages: Message[];
}

export interface StarterPrompt {
  kicker: string;
  text: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toReachRow(value: unknown): ReachRow | null {
  if (!isRecord(value)) return null;
  const { key, name, team, points, max } = value;
  if (typeof key !== "string" || typeof name !== "string" || typeof team !== "string") return null;
  if (typeof points !== "number" || typeof max !== "number") return null;
  return { key, name, team, points, max };
}

function toReachChart(value: unknown): ReachChartData | null {
  if (!isRecord(value) || value.kind !== "reach") return null;
  const { title, championship, year, rows } = value;
  if (typeof title !== "string" || typeof year !== "number" || !Array.isArray(rows)) return null;
  if (championship !== "drivers" && championship !== "constructors") return null;
  const parsed = (rows as unknown[]).map(toReachRow);
  if (parsed.some((row) => row === null)) return null;
  return { kind: "reach", title, championship, year, rows: parsed as ReachRow[] };
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? (value as unknown[]).filter((item): item is string => typeof item === "string") : [];
}

/** An `[ANSWER_DATA]` payload, keeping only what is well formed; `null` when it is not an object. */
export function toAnswerData(value: unknown): AnswerData | null {
  if (!isRecord(value)) return null;
  const charts = Array.isArray(value.charts) ? (value.charts as unknown[]).map(toReachChart) : [];
  return {
    subject: typeof value.subject === "string" ? value.subject : null,
    sources: strings(value.sources),
    charts: charts.filter((chart): chart is ReachChartData => chart !== null),
  };
}

const MARKER = /\[(TOOL_START|TOOL_END|ANSWER_DATA)\]([\s\S]*?)\[\/\1\]/g;
const OPENERS = ["[TOOL_START]", "[TOOL_END]", "[ANSWER_DATA]"];

export interface ParsedStream {
  content: string;
  toolStatus: string | null;
  data: AnswerData | null;
}

function parseData(body: string): AnswerData | null {
  try {
    return toAnswerData(JSON.parse(body));
  } catch {
    return null;
  }
}

/** Cuts a marker still arriving: an opener with no closer yet, or the first letters of one at the very end. */
function cutUnfinishedMarker(text: string): string {
  const starts = OPENERS.map((opener) => text.indexOf(opener)).filter((index) => index !== -1);
  if (starts.length > 0) return text.slice(0, Math.min(...starts));
  const tail = /\[[A-Z_]*$/.exec(text)?.[0];
  return tail && OPENERS.some((opener) => opener.startsWith(tail)) ? text.slice(0, -tail.length) : text;
}

/**
 * The whole stream received so far, read again on each chunk so a marker split
 * across two chunks is never lost: the answer text without markers, the tool
 * the engineer is running now, and the answer's data.
 */
export function parseChatStream(raw: string, done: boolean): ParsedStream {
  let toolStatus: string | null = null;
  let data: AnswerData | null = null;
  for (const [, kind, body] of raw.matchAll(MARKER)) {
    if (kind === "TOOL_START") toolStatus = body;
    else if (kind === "TOOL_END") toolStatus = null;
    else data = parseData(body);
  }
  const text = raw.replace(MARKER, "");
  return { content: done ? text.trim() : cutUnfinishedMarker(text), toolStatus, data };
}

export interface HistoryEntry {
  chat: Chat;
  /** True for the thread just deleted: its row reads as an undo line. */
  deleted: boolean;
}

export interface HistoryGroup {
  label: "Today" | "Earlier";
  entries: HistoryEntry[];
}

function sameDay(a: number, b: number): boolean {
  return new Date(a).toDateString() === new Date(b).toDateString();
}

/** The threads newest first, as "Today" (the reader's calendar day) and "Earlier"; an empty group is left out. */
export function historyGroups(chats: readonly Chat[], now: number, deleted: Chat | null = null): HistoryGroup[] {
  const entries: HistoryEntry[] = [
    ...chats.map((chat) => ({ chat, deleted: false })),
    ...(deleted ? [{ chat: deleted, deleted: true }] : []),
  ].sort((a, b) => b.chat.updatedAt - a.chat.updatedAt);
  const today = entries.filter((entry) => sameDay(entry.chat.updatedAt, now));
  const earlier = entries.filter((entry) => !today.includes(entry));
  return [
    { label: "Today" as const, entries: today },
    { label: "Earlier" as const, entries: earlier },
  ].filter((group) => group.entries.length > 0);
}

/** The line over an answer: the engineer, and what the answer read. */
export function answerHeader(subject: string | null | undefined): string {
  return subject ? `Engineer · ${subject}` : "Engineer";
}

const RULES_PROMPT: StarterPrompt = {
  kicker: "Rules",
  text: "When does a parc fermé change mean a pit-lane start?",
};

function titlePrompt(stakes: TableStakes, subject: "drivers" | "constructors"): StarterPrompt {
  const drivers = subject === "drivers";
  const kicker = drivers ? "Drivers' championship" : "Constructors' championship";
  const { leader } = stakes;
  if (stakes.decided) return { kicker, text: `Who can still finish second in the ${subject}' championship?` };
  const rival = stakes.contenders.find((contender) => contender.alive && contender.position !== 1);
  if (stakes.rivals_alive === 1 && rival) {
    return {
      kicker,
      text: drivers
        ? `Can ${rival.name} still catch ${leader.name}?`
        : `Can ${rival.name} still beat ${leader.name} to the constructors' title?`,
    };
  }
  return {
    kicker,
    text: drivers
      ? `Who can still catch ${leader.name} for the drivers' title?`
      : `Who can still beat ${leader.name} to the constructors' title?`,
  };
}

const WEEKEND: Record<string, { state: string; question: (name: string) => string }> = {
  upcoming: { state: "Upcoming", question: (name) => `Who does the model favour for the ${name}?` },
  in_progress: { state: "Weekend live", question: (name) => `What has happened so far at the ${name}?` },
  completed: { state: "Completed", question: (name) => `What decided the ${name}?` },
};

function weekendPrompt(race: NonNullable<OverviewShell["race"]>): StarterPrompt[] {
  const weekend = WEEKEND[race.status];
  if (!weekend) return [];
  return [{ kicker: `Round ${race.round} · ${weekend.state}`, text: weekend.question(race.name) }];
}

function standingsChip(stakes: NonNullable<OverviewShell["stakes"]>): string[] {
  if (stakes.as_of_round === null) return [];
  const base = stakes.sources.find((source) => source.role === "base");
  const name = base?.version ? `f1db ${base.version}` : "f1db";
  return [`${name} · standings after R${stakes.as_of_round}${stakes.provisional ? " · provisional" : ""}`];
}

/**
 * The starter prompts for an empty thread, and the chips naming the data they
 * were computed from. Each prompt is a question, never a result; one with no
 * data behind it is left out, so a pending or failed shell leaves the rules
 * question alone.
 */
export function starterPrompts(shell: OverviewShell | undefined): { prompts: StarterPrompt[]; sources: string[] } {
  const stakes = shell?.stakes;
  const race = shell?.race;
  const prompts = [
    ...(stakes?.drivers ? [titlePrompt(stakes.drivers, "drivers")] : []),
    ...(stakes?.constructors ? [titlePrompt(stakes.constructors, "constructors")] : []),
    ...(race ? weekendPrompt(race) : []),
    RULES_PROMPT,
  ];
  const sources = [...(stakes ? standingsChip(stakes) : []), ...(race ? [`calendar · round ${race.round}`] : [])];
  return { prompts, sources };
}
