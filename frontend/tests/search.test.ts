import { describe, expect, it } from "vitest";

import type { IdeaSearch, SearchHit } from "../src/api";
import {
  countByRelevance,
  filterHits,
  isSearchRunning,
  relevanceLabel,
  searchProgress,
  searchRangeLabel,
  searchScopeLabel,
  searchStatusLine,
  searchWhenLabel,
  sortSearchesNewestFirst,
} from "../src/search";

function hit(id: number, over: Partial<SearchHit> = {}): SearchHit {
  return {
    id,
    email_id: 10 + id,
    relevance: "direct",
    title: `Finding ${id}`,
    excerpt: "Harness choice moved SWE-bench scores by 12 points.",
    why_relevant: "Reports a measured harness effect.",
    email_title: "[AINews] Aug 18",
    email_date: "2026-08-18",
    date_iso: "2026-08-18",
    candidate_id: null,
    ...over,
  };
}

function search(over: Partial<IdeaSearch> = {}): IdeaSearch {
  return {
    id: 1,
    question: "which studies link harnesses to benchmark scores?",
    date_from: null,
    date_to: null,
    status: "done",
    emails_total: 12,
    chunks_total: 3,
    chunks_done: 3,
    chunks_failed: 0,
    hits_total: 5,
    error: null,
    created_at: "2026-08-19T04:00:00",
    finished_at: "2026-08-19T04:08:00",
    phase: "done",
    listed: 0,
    new_emails: 0,
    skipped: 0,
    current: 0,
    ...over,
  };
}

describe("running state", () => {
  it("treats queued and running as in progress", () => {
    expect(isSearchRunning(search({ status: "queued" }))).toBe(true);
    expect(isSearchRunning(search({ status: "running" }))).toBe(true);
  });

  it("treats finished, failed and missing searches as not running", () => {
    expect(isSearchRunning(search({ status: "done" }))).toBe(false);
    expect(isSearchRunning(search({ status: "failed" }))).toBe(false);
    expect(isSearchRunning(null)).toBe(false);
  });
});

describe("filterHits", () => {
  const hits = [
    hit(1, { relevance: "direct", title: "SWE-bench Pro spread" }),
    hit(2, { relevance: "related", title: "Agent Arena cost filters" }),
    hit(3, { relevance: "direct", title: "Terminal-Bench harness ablation" }),
  ];

  it("shows everything by default", () => {
    expect(filterHits(hits, { view: "all" }).map((h) => h.id)).toEqual([1, 2, 3]);
  });

  it("narrows to one relevance level", () => {
    expect(filterHits(hits, { view: "direct" }).map((h) => h.id)).toEqual([1, 3]);
    expect(filterHits(hits, { view: "related" }).map((h) => h.id)).toEqual([2]);
  });

  it("matches text across the title, quote, commentary and email", () => {
    expect(filterHits(hits, { view: "all", search: "arena" }).map((h) => h.id)).toEqual([2]);
    expect(filterHits(hits, { view: "all", search: "12 points" })).toHaveLength(3);
    expect(filterHits(hits, { view: "all", search: "measured harness" })).toHaveLength(3);
    expect(filterHits(hits, { view: "all", search: "Aug 18" })).toHaveLength(3);
  });

  it("ignores case and surrounding spaces in the query", () => {
    expect(filterHits(hits, { view: "all", search: "  ABLATION " }).map((h) => h.id)).toEqual([3]);
  });

  it("combines the relevance filter with the text query", () => {
    const found = filterHits(hits, { view: "direct", search: "arena" });
    expect(found).toEqual([]);
  });

  it("counts each relevance level", () => {
    expect(countByRelevance(hits)).toEqual({ direct: 2, related: 1 });
  });

  it("labels an unknown relevance as related rather than blank", () => {
    expect(relevanceLabel("direct")).toBe("Direct answer");
    expect(relevanceLabel("weird")).toBe("Related");
    expect(countByRelevance([hit(1, { relevance: "weird" })])).toEqual({
      direct: 0,
      related: 1,
    });
  });
});

describe("searchProgress", () => {
  it("is indeterminate until the batches have been counted", () => {
    expect(searchProgress(search({ chunks_total: 0, chunks_done: 0 }))).toEqual({
      pct: 0,
      determinate: false,
    });
  });

  it("tracks completed batches", () => {
    expect(searchProgress(search({ chunks_total: 4, chunks_done: 1 })).pct).toBe(25);
  });

  it("tracks Gmail download against the listed count", () => {
    expect(
      searchProgress(
        search({
          status: "running",
          phase: "fetching",
          listed: 4,
          current: 1,
          chunks_total: 0,
        }),
      ),
    ).toEqual({ pct: 25, determinate: true });
  });

  it("is indeterminate while Gmail is still listing", () => {
    expect(searchProgress(search({ status: "running", phase: "listing" }))).toEqual({
      pct: 0,
      determinate: false,
    });
  });

  it("counts a failed batch as finished so the bar cannot stall", () => {
    const p = searchProgress(search({ chunks_total: 4, chunks_done: 2, chunks_failed: 2 }));
    expect(p).toEqual({ pct: 100, determinate: true });
  });
});

describe("status and scope wording", () => {
  it("names the batch being read and the findings so far", () => {
    const line = searchStatusLine(
      search({ status: "running", chunks_total: 3, chunks_done: 1, hits_total: 4 }),
    );
    expect(line).toBe("Reading batch 2 of 3 · 4 findings so far");
  });

  it("does not claim a batch number before the count is known", () => {
    const line = searchStatusLine(
      search({ status: "running", chunks_total: 0, chunks_done: 0, hits_total: 0 }),
    );
    expect(line).toBe("Starting the search · 0 findings so far");
  });

  it("never announces a batch beyond the total", () => {
    const line = searchStatusLine(
      search({ status: "running", chunks_total: 2, chunks_done: 2, hits_total: 9 }),
    );
    expect(line).toContain("batch 2 of 2");
  });

  it("summarises a finished search and flags skipped batches", () => {
    expect(searchStatusLine(search({ hits_total: 1, emails_total: 1 }))).toBe(
      "1 finding across 1 email",
    );
    expect(searchStatusLine(search({ chunks_failed: 1 }))).toBe(
      "5 findings across 12 emails · 1 batch failed",
    );
  });

  it("surfaces the failure reason", () => {
    expect(searchStatusLine(search({ status: "failed", error: "no api key" }))).toBe(
      "Search failed: no api key",
    );
    expect(searchStatusLine(search({ status: "failed", error: null }))).toBe("Search failed.");
  });

  it("describes the work a range implies", () => {
    expect(
      searchScopeLabel({
        emails: 12,
        stored: 12,
        will_fetch: 0,
        gmail_connected: true,
        chunks: 3,
      }),
    ).toBe("12 stored");
    expect(
      searchScopeLabel({
        emails: 1,
        stored: 1,
        will_fetch: 0,
        gmail_connected: false,
        chunks: 1,
      }),
    ).toBe("1 stored");
    expect(
      searchScopeLabel({
        emails: 0,
        stored: 0,
        will_fetch: 0,
        gmail_connected: false,
        chunks: 0,
      }),
    ).toBe("No stored emails. Connect Gmail to pull them.");
  });

  it("says when missing issues will be pulled from Gmail", () => {
    expect(
      searchScopeLabel({
        emails: 14,
        stored: 12,
        will_fetch: 2,
        gmail_connected: true,
        chunks: 4,
      }),
    ).toBe("12 stored · 2 new from Gmail");
  });

  it("names the Gmail download while a search is fetching", () => {
    expect(
      searchStatusLine(
        search({
          status: "running",
          phase: "fetching",
          listed: 0,
          current: 0,
          hits_total: 0,
        }),
      ),
    ).toBe("Downloading emails…");
    expect(
      searchStatusLine(
        search({
          status: "running",
          phase: "fetching",
          listed: 20,
          current: 3,
          hits_total: 0,
        }),
      ),
    ).toBe("Downloading 3 of 20 emails");
  });

  it("mentions pulled emails on a finished search", () => {
    expect(searchStatusLine(search({ hits_total: 1, emails_total: 2, new_emails: 1 }))).toBe(
      "1 finding across 2 emails · pulled 1 from Gmail",
    );
  });

  it("describes open-ended and partial date ranges", () => {
    expect(searchRangeLabel(search())).toBe("all stored emails");
    expect(searchRangeLabel(search({ date_from: "2026-08-01", date_to: "2026-08-19" }))).toBe(
      "2026-08-01 – 2026-08-19",
    );
    expect(searchRangeLabel(search({ date_from: "2026-08-01" }))).toBe("from 2026-08-01");
    expect(searchRangeLabel(search({ date_to: "2026-08-19" }))).toBe("through 2026-08-19");
  });

  it("lists past searches newest first", () => {
    const older = search({ id: 1, created_at: "2026-08-18T04:00:00", question: "older" });
    const newer = search({ id: 2, created_at: "2026-08-19T04:00:00", question: "newer" });
    expect(sortSearchesNewestFirst([older, newer]).map((s) => s.id)).toEqual([2, 1]);
    expect(sortSearchesNewestFirst([newer, older]).map((s) => s.id)).toEqual([2, 1]);
  });

  it("breaks a created_at tie with the higher id first", () => {
    const a = search({ id: 3, created_at: "2026-08-19T04:00:00" });
    const b = search({ id: 9, created_at: "2026-08-19T04:00:00" });
    expect(sortSearchesNewestFirst([a, b]).map((s) => s.id)).toEqual([9, 3]);
  });

  it("formats a search timestamp rather than leaving it blank", () => {
    expect(searchWhenLabel("2026-08-19T09:32:00")).toMatch(/2026/);
    expect(searchWhenLabel("")).toBe("");
  });
});
