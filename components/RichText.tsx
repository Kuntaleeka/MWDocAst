import { Fragment, type ReactNode } from "react";
import type { Citation } from "@/lib/api";

/**
 * Minimal Markdown for model answers: paragraphs, bullet/numbered lists, **bold**, `code`, and
 * [S1] citation chips. Everything is rendered as React text nodes, never as HTML, so document or
 * model content can't inject markup.
 */
export function RichText({ text, citations }: { text: string; citations: Citation[] }) {
  const byLabel = new Map(citations.map((c) => [c.label, c]));
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;

  const flushList = () => {
    if (!list) return;
    const Tag = list.ordered ? "ol" : "ul";
    blocks.push(
      <Tag key={blocks.length} className={`${list.ordered ? "list-decimal" : "list-disc"} ml-5 flex flex-col gap-0.5`}>
        {list.items.map((item, i) => (
          <li key={i}>{inline(item, byLabel)}</li>
        ))}
      </Tag>,
    );
    list = null;
  };

  for (const para of text.split(/\n{2,}/)) {
    for (const line of para.split("\n")) {
      const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
      const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
      const item = bullet ?? numbered;
      if (item) {
        const ordered = Boolean(numbered);
        if (list && list.ordered !== ordered) flushList();
        list ??= { ordered, items: [] };
        list.items.push(item[1]);
      } else if (line.trim()) {
        flushList();
        blocks.push(<p key={blocks.length}>{inline(line, byLabel)}</p>);
      }
    }
    flushList();
  }
  return <div className="flex flex-col gap-2">{blocks}</div>;
}

function inline(text: string, byLabel: Map<string, Citation>): ReactNode {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[S\d+\])/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4)
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2)
      return (
        <code key={i} className="rounded-md bg-subtle px-1.5 py-0.5 font-mono text-[0.85em]">
          {part.slice(1, -1)}
        </code>
      );
    const c = /^\[S\d+\]$/.test(part) ? byLabel.get(part.slice(1, -1)) : undefined;
    if (c)
      return (
        <sup
          key={i}
          title={`${c.filename}${c.section ? ` § ${c.section}` : ""}`}
          className="mx-0.5 cursor-help rounded-md bg-accent-soft px-1 py-px font-mono text-[0.65rem] font-semibold text-accent"
        >
          {c.label}
        </sup>
      );
    return <Fragment key={i}>{part}</Fragment>;
  });
}
