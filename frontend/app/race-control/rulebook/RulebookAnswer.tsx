import { PanelHeading } from "@/app/ui/PanelHeading";
import { Section } from "@/app/ui/section/Section";

import { Panel } from "../components/RaceControlPrimitives";

import {
  answerCopy,
  decisionBody,
  decisionLead,
  decisionMatch,
  markupParts,
  passageLabel,
  type MarkupPart,
  type RulebookArticle,
  type RulebookDecision,
  type RulebookSearched,
} from "./rulebookModel";

const LABEL = "block font-mono text-[10px] font-medium uppercase leading-[1.6] tracking-[0.08em] text-rc-ink-3";
const NOTE = "mt-3.5 font-mono text-[10px] font-medium uppercase leading-[1.6] tracking-[0.1em] text-rc-ink-3";

function Markup({ part }: { part: MarkupPart }) {
  if (part.kind === "bold") return <b className="font-semibold text-rc-ink">{part.value}</b>;
  if (part.kind === "cite") {
    return (
      <span className="mx-0.5 rounded-[3px] bg-f1-red/14 px-[5px] py-0.5 font-mono text-[10px] font-semibold leading-none text-rc-red-text">
        <span className="sr-only">source </span>
        {part.value}
      </span>
    );
  }
  return <>{part.value}</>;
}

function Source({ cite, children }: { cite: number; children: React.ReactNode }) {
  return (
    <li className="grid grid-cols-[34px_minmax(0,1fr)] gap-3 rounded-md border border-rc-line bg-(--surface) p-3.5">
      <b className="font-display text-xl font-extrabold leading-none text-rc-red-text">{cite}</b>
      <div className="min-w-0 text-[13px] text-rc-ink-2 [overflow-wrap:anywhere]">{children}</div>
    </li>
  );
}

function PassageSource({ article, year }: { article: RulebookArticle; year: number }) {
  return (
    <Source cite={article.cite}>
      <span className={LABEL}>{passageLabel(article, year)}</span>
      {article.excerpt}
    </Source>
  );
}

function DecisionSource({
  decision,
  year,
  match,
}: {
  decision: RulebookDecision;
  year: number;
  match: "article" | "keyword";
}) {
  return (
    <Source cite={decision.cite}>
      <span className={LABEL}>
        {decisionLead(decision, year)}
        <a
          href={decision.url}
          target="_blank"
          rel="noreferrer"
          className="underline decoration-rc-dim underline-offset-2 hover:text-rc-ink"
        >
          Document {decision.number}
        </a>
        {decisionMatch(decision, match)}
      </span>
      {decisionBody(decision)}
    </Source>
  );
}

function SummaryPanel({ answer, className = "" }: { answer: RulebookSearched; className?: string }) {
  const { summary, decisions, year } = answer;
  const { eyebrow, note } = answerCopy(answer);
  return (
    <Panel className={`p-6 ${className}`}>
      <PanelHeading as="h2" eyebrow={eyebrow} title={summary.heading} />
      <p className="max-w-[76ch] text-[15px] leading-[1.7] text-rc-ink-2">
        {markupParts(summary.paragraph).map((part, index) => (
          <Markup key={`${index}-${part.kind}`} part={part} />
        ))}
      </p>
      <ol className="mt-5 grid gap-2.5">
        {answer.articles.map((article) => (
          <PassageSource key={article.cite} article={article} year={year} />
        ))}
        {decisions.items.map((decision) => (
          <DecisionSource key={decision.cite} decision={decision} year={year} match={decisions.match} />
        ))}
      </ol>
      <p className={NOTE}>{note}</p>
    </Panel>
  );
}

interface RulebookAnswerProps {
  answer: RulebookSearched;
  retry: () => void;
  refreshing: boolean;
}

/** The answer card; with the rule index off, the failed passage card above the keyword matches. */
export function RulebookAnswer({ answer, retry, refreshing }: RulebookAnswerProps) {
  if (answer.status !== "keyword") return <SummaryPanel answer={answer} />;
  return (
    <>
      <Section state={{ status: "failed", reason: answer.reason, refreshing, retry }} label="Regulation passages">
        {null}
      </Section>
      <SummaryPanel answer={answer} className="mt-2.5" />
    </>
  );
}
