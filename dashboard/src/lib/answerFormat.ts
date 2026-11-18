/**
 * Tiny, safe formatter for the AI answer on /ask.
 *
 * The model answers in a small Markdown subset: **bold**, offer links
 * `[Titel](#<offer id>)` and `* ` bullet lines. Rendering it as plain text
 * showed raw asterisks and UUIDs to shoppers. We parse just that subset into
 * data — React renders it, so no HTML from the model ever reaches the page.
 */

export type Part =
  | { kind: "text"; text: string }
  | { kind: "bold"; text: string }
  | { kind: "offer"; text: string; id: string };

export type Block = { bullet: boolean; parts: Part[] };

const INLINE = /\*\*(.+?)\*\*|\[([^\]]+)\]\(#([^)\s]+)\)/g;

export function parseInline(line: string): Part[] {
  const parts: Part[] = [];
  let last = 0;
  for (const m of line.matchAll(INLINE)) {
    const at = m.index ?? 0;
    if (at > last) parts.push({ kind: "text", text: line.slice(last, at) });
    if (m[1] != null) parts.push({ kind: "bold", text: m[1] });
    else parts.push({ kind: "offer", text: m[2], id: m[3] });
    last = at + m[0].length;
  }
  if (last < line.length) parts.push({ kind: "text", text: line.slice(last) });
  return parts;
}

/** Paragraphs and bullet items; blank lines dropped. */
export function parseAnswer(answer: string): Block[] {
  return answer
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => {
      const bullet = /^[*\-•]\s+/.test(l);
      return { bullet, parts: parseInline(bullet ? l.replace(/^[*\-•]\s+/, "") : l) };
    });
}
