import { useEffect, useMemo, useRef, type ReactNode } from "react";

import { findHitIndex, parseBlocks, type Block } from "./excerpt";

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
