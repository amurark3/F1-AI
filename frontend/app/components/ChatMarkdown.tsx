"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

// The engineer answers in Markdown — bold callouts, headings, and the result
// tables its tools return verbatim — so the reply has to be parsed, not printed.
// GFM is what adds tables. Raw HTML in the reply is not rendered (react-markdown's
// default), and unsafe link protocols are stripped: this is model output.
// Headings are demoted: the page already owns h1/h2, and a reply is one
// section inside it. Tools emit `###` titles; the model mixes in `#` and `##`.
// Colour follows the Race Control palette: red marks structure (heading rules,
// bullets, callouts), blue marks links, and everything else stays neutral.
const SectionHeading: Components["h1"] = ({ children }) => (
  <h3 className="mb-2 mt-5 flex items-center gap-2 text-[13px] font-black uppercase tracking-[0.08em] text-white first:mt-0">
    <span aria-hidden="true" className="h-3 w-[3px] shrink-0 rounded-full bg-[#E10600]" />
    {children}
  </h3>
);

const COMPONENTS: Components = {
  p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
  em: ({ children }) => <em className="italic text-[#B7BDCA]">{children}</em>,
  h1: SectionHeading,
  h2: SectionHeading,
  h3: ({ children }) => <h4 className="mb-2 mt-4 text-sm font-bold text-white first:mt-0">{children}</h4>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5 marker:text-[#FF4655]">{children}</ul>,
  ol: ({ children }) => (
    <ol className="my-2 list-decimal space-y-1 pl-5 marker:font-mono marker:text-[#7F8797]">{children}</ol>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-[#9EC5FF] underline decoration-[#9EC5FF]/40 underline-offset-2 transition-colors hover:text-white hover:decoration-white/60"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-3 rounded-r-md border-l-2 border-[#E10600]/60 bg-[#E10600]/[0.05] px-3 py-2 text-[#C9CED8]">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-4 border-[#1E2633]" />,
  code: ({ children }) => (
    <code className="rounded border border-[#1E2633] bg-[#121825] px-1 py-0.5 font-mono text-[0.85em] text-[#E8E8E8]">
      {children}
    </code>
  ),
  pre: ({ children }) => (
    <pre className="my-2 overflow-x-auto rounded-md border border-[#1E2633] bg-[#080B11] p-3 [&>code]:border-0 [&>code]:bg-transparent [&>code]:p-0">
      {children}
    </pre>
  ),
  // Tool tables run to 20 rows and several columns; scroll them inside the
  // bubble rather than letting them push the page sideways.
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-md border border-[#1E2633] bg-[#0A0E16]">
      <table className="w-full border-collapse text-left text-xs tabular-nums">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-[#121825] text-[#7F8797]">{children}</thead>,
  tbody: ({ children }) => (
    <tbody className="[&>tr:hover]:bg-white/[0.04] [&>tr:nth-child(even)]:bg-white/[0.02] [&>tr>td:first-child]:text-white">
      {children}
    </tbody>
  ),
  th: ({ children }) => (
    <th className="whitespace-nowrap px-3 py-2 font-mono text-[10px] font-bold uppercase tracking-[0.14em]">
      {children}
    </th>
  ),
  td: ({ children }) => <td className="border-t border-[#1E2633] px-3 py-1.5 text-[#C9CED8]">{children}</td>,
};

const REMARK_PLUGINS = [remarkGfm];

export default function ChatMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown remarkPlugins={REMARK_PLUGINS} components={COMPONENTS}>
      {content}
    </ReactMarkdown>
  );
}
