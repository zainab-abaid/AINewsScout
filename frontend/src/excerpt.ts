/**
 * Splitting an email body into blocks, and locating the block an excerpt came
 * from so the reader can be scrolled to it.
 */

export type Block =
  | { kind: "h"; level: number; text: string; raw: string }
  | { kind: "hr"; raw: string }
  | { kind: "ul"; items: string[]; raw: string }
  | { kind: "p"; text: string; raw: string };

export function parseBlocks(md: string): Block[] {
  const chunks = md
    .replace(/\r\n/g, "\n")
    .split(/\n{2,}/)
    .map((s) => s.trim())
    .filter(Boolean);
  return chunks.map((chunk) => {
    const hm = /^(#{1,3})\s+(.+)$/.exec(chunk);
    if (hm && !chunk.includes("\n")) {
      return { kind: "h", level: hm[1].length, text: hm[2], raw: chunk };
    }
    if (/^---+$/.test(chunk)) return { kind: "hr", raw: chunk };
    const lines = chunk.split("\n");
    if (lines.length && lines.every((l) => /^\s*[-*]\s+/.test(l) || l.trim() === "")) {
      return {
        kind: "ul",
        items: lines.filter((l) => l.trim()).map((l) => l.replace(/^\s*[-*]\s+/, "")),
        raw: chunk,
      };
    }
    return { kind: "p", text: chunk.replace(/\n/g, " "), raw: chunk };
  });
}

/**
 * Reduces text to lowercase words. Punctuation, list markers and link syntax
 * are dropped, so an excerpt still matches the body when the two were produced
 * by different converters: a newsletter's `[ https://host/x ]` and Markdown's
 * `[label](https://host/x)` both collapse to the words around them.
 */
export function normalizeForMatch(s: string): string {
  return s
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, " $1 ")
    .replace(/https?:\/\/\S+/g, " ")
    .replace(/[^0-9A-Za-z\u00C0-\u024F]+/g, " ")
    .trim()
    .toLowerCase();
}

const PROBE_WORDS = 6;
const MAX_PROBES = 60;

/** Word windows spread across the whole excerpt. */
function probesFor(excerpt: string): string[] {
  const words = normalizeForMatch(excerpt).split(" ").filter(Boolean);
  if (words.length < PROBE_WORDS) return [];
  const last = words.length - PROBE_WORDS;
  const step = last > 0 ? Math.max(1, Math.ceil(last / (MAX_PROBES - 1))) : 1;
  const probes: string[] = [];
  for (let i = 0; i <= last; i += step) {
    probes.push(words.slice(i, i + PROBE_WORDS).join(" "));
  }
  return probes;
}

/**
 * The block matching the most probes. Scoring beats a single lookup because the
 * model writes its own lead-in ("Topic: ...") ahead of the quoted passage, and
 * an excerpt can straddle a heading and the list under it.
 */
export function findHitIndex(blocks: Block[], excerpt: string): number {
  const probes = probesFor(excerpt);
  if (!probes.length) return -1;
  let best = -1;
  let bestScore = 0;
  for (let i = 0; i < blocks.length; i++) {
    const hay = normalizeForMatch(blocks[i].raw);
    let score = 0;
    for (const probe of probes) if (hay.includes(probe)) score += 1;
    if (score > bestScore) {
      best = i;
      bestScore = score;
    }
  }
  return bestScore > 0 ? best : -1;
}
