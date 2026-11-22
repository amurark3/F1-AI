"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

// The engineer answers in Markdown — bold callouts, headings, and the result
// tables its tools return verbatim — so the reply has to be parsed, not printed.
// GFM is what adds tables. Raw HTML in the reply is not rendered (react-markdown's
// default), and unsafe link protocols are stripped: this is model output.
// Headings are demoted: the page already owns h1, and a reply is one section
// inside it. Tools emit `###` titles; the model mixes in `#` and `##`.
// Red marks structure (heading rules, quote bars), blue marks links (info),
// and everything else stays neutral.
const SectionHeading: Components["h1"] = ({ children }) => (
  <h3 className="mb-2 mt-5 flex items-center gap-2 text-[13px] font-bold uppercase tracking-[0.08em] text-rc-ink first:mt-0">
    <span aria-hidden="true" className="h-3 w-[3px] shrink-0 rounded-full bg-f1-red" />
    {children}
  </h3>
);

/** A column GFM aligns to the right: figures, in mono. */
function isRight(align: string | undefined, style: { textAlign?: string } | undefined): boolean {
  return align === "right" || style?.textAlign === "right";
}

const CELL_RIGHT = "text-right font-mono";

const COMPONENTS: Components = {
  p: ({ children }) => <p className="my-2.5 text-sm leading-[1.65] text-rc-ink-2 first:mt-0 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-rc-ink">{children}</strong>,
  em: ({ children }) => <em className="italic text-rc-ink-2">{children}</em>,
  h1: SectionHeading,
  h2: SectionHeading,
  h3: ({ children }) => <h4 className="mb-2 mt-4 text-sm font-semibold text-rc-ink first:mt-0">{children}</h4>,
  ul: ({ children }) => (
    <ul className="my-2 list-disc space-y-1 pl-5 text-sm text-rc-ink-2 marker:text-rc-ink-3">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="my-2 list-decimal space-y-1 pl-5 text-sm text-rc-ink-2 marker:font-mono marker:text-rc-ink-3">
      {children}
    </ol>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-rc-blue underline decoration-rc-blue/40 underline-offset-2 transition-colors hover:text-rc-ink"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-3 rounded-r-md border-l-2 border-f1-red/60 bg-f1-red/[0.05] px-3 py-2 text-rc-ink-2">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-4 border-rc-line" />,
  code: ({ children }) => (
    <code className="rounded border border-rc-line bg-rc-raised px-1 py-0.5 font-mono text-[0.85em] text-rc-ink">
      {children}
    </code>
  ),
  pre: ({ children }) => (
    <pre className="my-2 overflow-x-auto rounded-md border border-rc-line bg-rc-hero p-3 [&>code]:border-0 [&>code]:bg-transparent [&>code]:p-0">
      {children}
    </pre>
  ),
  // Tool tables run to 20 rows and several columns; they scroll inside their own box
  // rather than pushing the page sideways.
  table: ({ children }) => (
    <div className="my-2.5 overflow-x-auto rounded-md border border-rc-line bg-(--surface) px-3.5 pb-1 pt-3">
      <table className="w-full border-collapse text-left text-[13px] tabular-nums">{children}</table>
    </div>
  ),
  tbody: ({ children }) => <tbody className="[&_tr:last-child>td]:border-0">{children}</tbody>,
  th: ({ children, align, style }) => (
    <th
      className={`whitespace-nowrap border-b border-rc-line pb-2.5 pr-2.5 text-left font-mono text-[10px] font-semibold uppercase leading-none tracking-[0.16em] text-rc-ink-3 ${isRight(align, style) ? CELL_RIGHT : ""}`}
    >
      {children}
    </th>
  ),
  td: ({ children, align, style }) => (
    <td
      className={`border-b border-rc-line-soft py-[9px] pr-2.5 text-rc-ink ${isRight(align, style) ? CELL_RIGHT : ""}`}
    >
      {children}
    </td>
  ),
};

const REMARK_PLUGINS = [remarkGfm];

export function AnswerMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown remarkPlugins={REMARK_PLUGINS} components={COMPONENTS}>
      {content}
    </ReactMarkdown>
  );
}
