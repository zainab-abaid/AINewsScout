import type { Candidate, Category } from "./api";

export const UNCATEGORISED = "__uncategorised__";

export type TagFilter = "high-priority" | "strong" | "possible";
export type MarkFilter = "important" | "shortlist";

export type FilterState = {
  tagFilters: Set<TagFilter>;
  markFilters: Set<MarkFilter>;
  search: string;
  dateFrom: string;
  dateTo: string;
  /**
   * Categories the user switched off. Empty means show everything, so a
   * category created after the filter was set stays visible.
   */
  hiddenCats: Set<string>;
};

export function categoryKey(categoryId: number | null | undefined): string {
  return categoryId ? String(categoryId) : UNCATEGORISED;
}

export function allCategoryKeys(categories: Category[]): string[] {
  return [UNCATEGORISED, ...categories.map((c) => String(c.id))];
}

export function isCategoryOn(hidden: Set<string>, key: string): boolean {
  return !hidden.has(key);
}

export function allCategoriesOn(hidden: Set<string>, categories: Category[]): boolean {
  return allCategoryKeys(categories).every((key) => !hidden.has(key));
}

export function onCategoryCount(hidden: Set<string>, categories: Category[]): number {
  return allCategoryKeys(categories).filter((key) => !hidden.has(key)).length;
}

export function toggleCategoryVisibility(
  hidden: Set<string>,
  key: string,
  checked: boolean,
): Set<string> {
  const next = new Set(hidden);
  if (checked) next.delete(key);
  else next.add(key);
  return next;
}

export function showAllCategories(): Set<string> {
  return new Set<string>();
}

export function hideAllCategories(categories: Category[]): Set<string> {
  return new Set(allCategoryKeys(categories));
}

export function filterCandidates(candidates: Candidate[], state: FilterState): Candidate[] {
  const q = state.search.trim().toLowerCase();
  return candidates.filter((c) => {
    if (c.deleted) return false;
    if (state.tagFilters.size > 0 && !state.tagFilters.has(c.tag_slug as TagFilter)) return false;
    if (state.markFilters.size > 0) {
      const hit =
        (state.markFilters.has("important") && c.important) ||
        (state.markFilters.has("shortlist") && c.shortlisted);
      if (!hit) return false;
    }
    if (state.dateFrom && c.date_iso && c.date_iso < state.dateFrom) return false;
    if (state.dateTo && c.date_iso && c.date_iso > state.dateTo) return false;
    if (q) {
      const blob = `${c.topic} ${c.main_idea} ${c.excerpt} ${c.email_title}`.toLowerCase();
      if (!blob.includes(q)) return false;
    }
    if (!isCategoryOn(state.hiddenCats, categoryKey(c.category_id))) return false;
    return true;
  });
}

/** Which marks the Marked tab is showing. */
export type MarkView = "all" | "important" | "shortlist";

export function isMarked(c: Candidate): boolean {
  return c.important || c.shortlisted;
}

/**
 * Items the user marked, newest mark first. Items marked before the app started
 * recording a timestamp have no date, so they sort last by id.
 */
export function filterMarkedCandidates(
  candidates: Candidate[],
  opts: { view: MarkView; hiddenCats: Set<string>; search?: string },
): Candidate[] {
  const q = (opts.search || "").trim().toLowerCase();
  const rows = candidates.filter((c) => {
    if (c.deleted) return false;
    if (!isMarked(c)) return false;
    if (opts.view === "important" && !c.important) return false;
    if (opts.view === "shortlist" && !c.shortlisted) return false;
    if (!isCategoryOn(opts.hiddenCats, categoryKey(c.category_id))) return false;
    if (q) {
      const blob = `${c.topic} ${c.main_idea} ${c.notes} ${c.email_title}`.toLowerCase();
      if (!blob.includes(q)) return false;
    }
    return true;
  });
  return rows.sort((a, b) => {
    if (a.marked_at && b.marked_at) return a.marked_at < b.marked_at ? 1 : -1;
    if (a.marked_at) return -1;
    if (b.marked_at) return 1;
    return b.id - a.id;
  });
}

export function filtersAreDefault(state: FilterState, categories: Category[]): boolean {
  return (
    state.tagFilters.size === 0 &&
    state.markFilters.size === 0 &&
    !state.search &&
    !state.dateFrom &&
    !state.dateTo &&
    allCategoriesOn(state.hiddenCats, categories)
  );
}
