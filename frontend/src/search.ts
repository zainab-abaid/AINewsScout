import type { IdeaSearch, SearchHit } from "./api";

/** Which findings the results list is showing. */
export type HitView = "all" | "direct" | "related";

export const RELEVANCE_LABEL: Record<string, string> = {
  direct: "Direct answer",
  related: "Related",
};

export function relevanceLabel(relevance: string): string {
  return RELEVANCE_LABEL[relevance] || "Related";
}

export function isSearchRunning(search: IdeaSearch | null | undefined): boolean {
  return !!search && (search.status === "queued" || search.status === "running");
}

export function filterHits(
  hits: SearchHit[],
  opts: { view: HitView; search?: string },
): SearchHit[] {
  const q = (opts.search || "").trim().toLowerCase();
  return hits.filter((h) => {
    if (opts.view !== "all" && h.relevance !== opts.view) return false;
    if (q) {
      const blob = `${h.title} ${h.excerpt} ${h.why_relevant} ${h.email_title}`.toLowerCase();
      if (!blob.includes(q)) return false;
    }
    return true;
  });
}

export function countByRelevance(hits: SearchHit[]): { direct: number; related: number } {
  return {
    direct: hits.filter((h) => h.relevance === "direct").length,
    related: hits.filter((h) => h.relevance !== "direct").length,
  };
}

/**
 * How far along the batches are. While Gmail is listing or downloading, the
 * bar tracks listed messages; once batches are counted it tracks those.
 */
export function searchProgress(search: IdeaSearch): { pct: number; determinate: boolean } {
  const phase = search.phase || "";
  if (phase === "listing") return { pct: 0, determinate: false };
  if (phase === "fetching") {
    const listed = search.listed || 0;
    if (listed <= 0) return { pct: 0, determinate: false };
    return { pct: Math.min(100, (search.current / listed) * 100), determinate: true };
  }
  const total = search.chunks_total;
  if (total <= 0) return { pct: 0, determinate: false };
  const done = Math.min(total, search.chunks_done + search.chunks_failed);
  return { pct: Math.min(100, (done / total) * 100), determinate: true };
}

export function searchScopeLabel(preview: {
  emails: number;
  stored: number;
  will_fetch: number;
  gmail_connected: boolean;
  chunks: number;
}): string {
  if (preview.will_fetch > 0) {
    const stored = preview.stored
      ? `${preview.stored} stored · `
      : "";
    return `${stored}${preview.will_fetch} new from Gmail`;
  }
  if (preview.emails <= 0) {
    return preview.gmail_connected
      ? "No emails in this range."
      : "No stored emails. Connect Gmail to pull them.";
  }
  return `${preview.emails} stored`;
}

export function searchStatusLine(search: IdeaSearch): string {
  const found = `${search.hits_total} finding${search.hits_total === 1 ? "" : "s"}`;
  if (isSearchRunning(search)) {
    const phase = search.phase || "";
    if (phase === "listing") return "Checking Gmail…";
    if (phase === "fetching") {
      const listed = search.listed || 0;
      const current = Math.min(search.current || 0, listed);
      if (listed > 0) return `Downloading ${current} of ${listed} emails`;
      return "Downloading emails…";
    }
    if (phase === "fetched") return "Download complete · starting the search";
    const at = Math.min(search.chunks_total, search.chunks_done + search.chunks_failed + 1);
    const where = search.chunks_total
      ? `Reading batch ${at} of ${search.chunks_total}`
      : "Starting the search";
    return `${where} · ${found} so far`;
  }
  if (search.status === "failed") {
    return search.error ? `Search failed: ${search.error}` : "Search failed.";
  }
  const skipped = search.chunks_failed
    ? ` · ${search.chunks_failed} batch${search.chunks_failed === 1 ? "" : "es"} failed`
    : "";
  const pulled =
    search.new_emails > 0
      ? ` · pulled ${search.new_emails} from Gmail`
      : "";
  return `${found} across ${search.emails_total} email${search.emails_total === 1 ? "" : "s"}${pulled}${skipped}`;
}

export function searchRangeLabel(search: IdeaSearch): string {
  if (search.date_from && search.date_to) return `${search.date_from} – ${search.date_to}`;
  if (search.date_from) return `from ${search.date_from}`;
  if (search.date_to) return `through ${search.date_to}`;
  return "all stored emails";
}

function parseSearchTime(iso: string): number {
  if (!iso) return NaN;
  const trimmed = iso.trim();
  if (/[zZ]$/.test(trimmed) || /[+-]\d{2}:?\d{2}$/.test(trimmed)) {
    return new Date(trimmed).getTime();
  }
  return new Date(`${trimmed}Z`).getTime();
}

/** When the search was run, in the viewer's local timezone. */
export function searchWhenLabel(iso: string): string {
  const ms = parseSearchTime(iso);
  if (!Number.isFinite(ms)) return "";
  return new Date(ms).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function sortSearchesNewestFirst<T extends { id: number; created_at: string }>(
  rows: T[],
): T[] {
  return [...rows].sort((a, b) => {
    if (a.created_at !== b.created_at) return a.created_at < b.created_at ? 1 : -1;
    return b.id - a.id;
  });
}
