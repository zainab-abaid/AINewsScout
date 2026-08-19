import { useEffect, useMemo, useRef, type ReactNode } from "react";

function hostLabel(href: string): string {
  try {
    return new URL(href).hostname.replace(/^www\./, "") || "link";
  } catch {
    return "link";
  }
}

function citationLabel(href: string): string {
  return `[${hostLabel(href)}]`;
}

function displayLabel(text: string, href: string): string {
  const t = text.trim();
  const host = hostLabel(href);
  if (!t || /^https?:\/\//i.test(t) || t === href || t === host || t === "link") {
    return citationLabel(href);
  }
  return t;
}

function safeHref(href: string): string | null {
  try {
    const u = new URL(href);
    if (u.protocol === "http:" || u.protocol === "https:") return href;
  } catch {
    /* ignore */
  }
  return null;
}

function SafeA({ href, children }: { href: string; children: ReactNode }) {
  const safe = safeHref(href);
  if (!safe) return <>{children}</>;
  return (
    <a href={safe} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}

function renderDecorated(text: string, key: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /`([^`]+)`|\*\*([^*]+)\*\*|\*([^*]+)\*/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    if (m[1] != null) nodes.push(<code key={`${key}-c${i}`}>{m[1]}</code>);
    else if (m[2] != null) nodes.push(<strong key={`${key}-b${i}`}>{m[2]}</strong>);
    else if (m[3] != null) nodes.push(<em key={`${key}-e${i}`}>{m[3]}</em>);
    last = m.index + m[0].length;
    i += 1;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function renderInline(text: string, key: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)|(https?:\/\/[^\s)<]+)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) nodes.push(...renderDecorated(text.slice(last, m.index), `${key}-t${i}`));
    if (m[1] != null && m[2] != null) {
      nodes.push(
        <SafeA key={`${key}-a${i}`} href={m[2]}>
          {displayLabel(m[1], m[2])}
        </SafeA>,
      );
    } else if (m[3]) {
      nodes.push(
        <SafeA key={`${key}-u${i}`} href={m[3]}>
          {citationLabel(m[3])}
        </SafeA>,
      );
    }
    last = m.index + m[0].length;
    i += 1;
  }
  if (last < text.length) nodes.push(...renderDecorated(text.slice(last), `${key}-t${i}`));
  return nodes;
}

export function MarkdownInline({ text }: { text: string }) {
  return <>{renderInline(text, "in")}</>;
}

type Block =
  | { kind: "h"; level: number; text: string; raw: string }
  | { kind: "hr"; raw: string }
  | { kind: "ul"; items: string[]; raw: string }
  | { kind: "p"; text: string; raw: string };

function parseBlocks(md: string): Block[] {
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

function plainish(s: string): string {
  return s
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, "$1")
    .replace(/https?:\/\/\S+/g, " ")
    .replace(/[#*_`>-]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function findHitIndex(blocks: Block[], excerpt: string): number {
  const needle = plainish(excerpt);
  if (needle.length < 24) return -1;
  const start = needle.slice(0, Math.min(96, needle.length));
  for (let i = 0; i < blocks.length; i++) {
    const hay = plainish(blocks[i].raw);
    if (hay.includes(start)) return i;
  }
  const words = start.split(" ").slice(0, 12).join(" ");
  if (words.length < 20) return -1;
  for (let i = 0; i < blocks.length; i++) {
    if (plainish(blocks[i].raw).includes(words)) return i;
  }
  return -1;
}

function BlockView({ block, hit }: { block: Block; hit: boolean }) {
  const hitProp = hit ? { "data-excerpt-hit": "true" } : {};
  if (block.kind === "hr") return <hr {...hitProp} />;
  if (block.kind === "h") {
    const Tag = (block.level === 1 ? "h1" : block.level === 2 ? "h2" : "h3") as "h1" | "h2" | "h3";
    return (
      <Tag {...hitProp}>
        <MarkdownInline text={block.text} />
      </Tag>
    );
  }
  if (block.kind === "ul") {
    return (
      <ul {...hitProp}>
        {block.items.map((item, i) => (
          <li key={i}>
            <MarkdownInline text={item} />
          </li>
        ))}
      </ul>
    );
  }
  return (
    <p {...hitProp}>
      <MarkdownInline text={block.text} />
    </p>
  );
}

export function MarkdownBody({ text, highlight }: { text: string; highlight?: string }) {
  const rootRef = useRef<HTMLDivElement>(null);
  const blocks = useMemo(() => parseBlocks(text), [text]);
  const hit = useMemo(() => findHitIndex(blocks, highlight || ""), [blocks, highlight]);

  useEffect(() => {
    const id = window.setTimeout(() => {
      rootRef.current?.querySelector("[data-excerpt-hit]")?.scrollIntoView({
        block: "center",
        behavior: "smooth",
      });
    }, 60);
    return () => window.clearTimeout(id);
  }, [text, highlight, hit]);

  return (
    <div ref={rootRef} className="email-body md">
      {blocks.map((block, i) => (
        <BlockView key={i} block={block} hit={i === hit} />
      ))}
    </div>
  );
}
