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
    const pull = `${preview.will_fetch} missing email${preview.will_fetch === 1 ? "" : "s"}`;
    const kept = preview.stored
      ? ` · ${preview.stored} already stored, not re-downloaded`
      : "";
    const c = `${preview.chunks} batch${preview.chunks === 1 ? "" : "es"}`;
    return `Will pull ${pull} from Gmail${kept}, then read ${preview.emails} in ${c}.`;
  }
  if (preview.emails <= 0) {
    return preview.gmail_connected
      ? "No emails in this range."
      : "No stored emails in this range. Connect Gmail to pull them.";
  }
  const e = `${preview.emails} email${preview.emails === 1 ? "" : "s"}`;
  const c = `${preview.chunks} batch${preview.chunks === 1 ? "" : "es"}`;
  return `Will read ${e} in ${c}, about 1–3 minutes per batch.`;
}

export function searchStatusLine(search: IdeaSearch): string {
  const found = `${search.hits_total} finding${search.hits_total === 1 ? "" : "s"}`;
  if (isSearchRunning(search)) {
    const phase = search.phase || "";
    if (phase === "listing") return "Checking Gmail for emails not stored yet";
    if (phase === "fetching") {
      const neu = search.new_emails || 0;
      const skipped = search.skipped || 0;
      return `Downloading missing emails · ${neu} new, ${skipped} already stored`;
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
