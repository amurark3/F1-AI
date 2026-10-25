"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

// The engineer answers in Markdown — bold callouts, headings, and the result
// tables its tools return verbatim — so the reply has to be parsed, not printed.
// GFM is what adds tables. Raw HTML in the reply is not rendered (react-markdown's
// default), and unsafe link protocols are stripped: this is model output.
// Headings are demoted: the page already owns h1/h2, and a reply is one
// section inside it. Tools emit `###` titles; the model mixes in `#` and `##`.
const SectionHeading: Components["h1"] = ({ children }) => (
  <h3 className="mb-2 mt-4 text-base font-black uppercase text-white first:mt-0">{children}</h3>
);

const COMPONENTS: Components = {
  p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-bold text-white">{children}</strong>,
  em: ({ children }) => <em className="italic text-neutral-300">{children}</em>,
  h1: SectionHeading,
  h2: SectionHeading,
  h3: ({ children }) => <h4 className="mb-2 mt-3 text-sm font-bold uppercase text-white first:mt-0">{children}</h4>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-[#00FF78] underline underline-offset-2">
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-[#00FF78]/40 pl-3 text-neutral-400">{children}</blockquote>
  ),
  hr: () => <hr className="my-4 border-[#1E2633]" />,
  code: ({ children }) => <code className="rounded bg-white/[0.06] px-1 py-0.5 text-[#00FF78]">{children}</code>,
  pre: ({ children }) => (
    <pre className="my-2 overflow-x-auto rounded-md border border-[#1E2633] bg-black/40 p-3 [&>code]:bg-transparent [&>code]:p-0">
      {children}
    </pre>
  ),
  // Tool tables run to 20 rows and several columns; scroll them inside the
  // bubble rather than letting them push the page sideways.
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-md border border-[#1E2633]">
      <table className="w-full border-collapse text-left text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-white/[0.04] text-neutral-400">{children}</thead>,
  th: ({ children }) => <th className="whitespace-nowrap px-3 py-2 font-bold uppercase">{children}</th>,
  td: ({ children }) => <td className="border-t border-[#1E2633] px-3 py-1.5">{children}</td>,
};

const REMARK_PLUGINS = [remarkGfm];

export default function ChatMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown remarkPlugins={REMARK_PLUGINS} components={COMPONENTS}>
      {content}
    </ReactMarkdown>
  );
}
