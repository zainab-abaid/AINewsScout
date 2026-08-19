import { describe, expect, it } from "vitest";

import type { Candidate, Category } from "../src/api";
import {
  UNCATEGORISED,
  allCategoriesOn,
  filterCandidates,
  filterMarkedCandidates,
  filtersAreDefault,
  hideAllCategories,
  isCategoryOn,
  onCategoryCount,
  showAllCategories,
  toggleCategoryVisibility,
  type FilterState,
} from "../src/filters";

function cat(id: number, name: string): Category {
  return { id, name, is_default: false, sort_order: id };
}

function candidate(id: number, categoryId: number | null): Candidate {
  return {
    id,
    email_id: 1,
    tag: "STRONG CANDIDATE",
    tag_slug: "strong",
    topic: `Topic ${id}`,
    main_idea: "idea",
    excerpt: "excerpt",
    important: false,
    shortlisted: false,
    deleted: false,
    processed: false,
    category_id: categoryId,
    category_name: "",
    notes: "",
    marked_at: "",
    email_title: "AINews",
    email_date: "2026-08-18",
    date_iso: "2026-08-18",
    from_addr: "news@example.com",
  };
}

function state(overrides: Partial<FilterState> = {}): FilterState {
  return {
    tagFilters: new Set(),
    markFilters: new Set(),
    search: "",
    dateFrom: "",
    dateTo: "",
    hiddenCats: showAllCategories(),
    ...overrides,
  };
}

describe("category visibility", () => {
  it("shows every candidate by default", () => {
    const items = [candidate(1, null), candidate(2, 3)];
    expect(filterCandidates(items, state())).toHaveLength(2);
  });

  it("keeps an item visible when it is moved into a brand new category", () => {
    // The user switches one existing category off.
    const hidden = toggleCategoryVisibility(showAllCategories(), "2", false);
    expect(isCategoryOn(hidden, "2")).toBe(false);
    expect(isCategoryOn(hidden, "1")).toBe(true);

    // A category created afterwards is unknown to that filter, and an item
    // moved into it must not vanish from the queue.
    const newCat = cat(99, "Agent skills");
    const visible = filterCandidates([candidate(7, newCat.id)], state({ hiddenCats: hidden }));
    expect(visible).toHaveLength(1);
    expect(isCategoryOn(hidden, String(newCat.id))).toBe(true);
  });

  it("hides only the category that was switched off", () => {
    const items = [candidate(1, 1), candidate(2, 2), candidate(3, null)];
    const hidden = toggleCategoryVisibility(showAllCategories(), "1", false);
    expect(filterCandidates(items, state({ hiddenCats: hidden })).map((c) => c.id)).toEqual([2, 3]);
  });

  it("treats uncategorised items as their own group", () => {
    const items = [candidate(1, null), candidate(2, 5)];
    const hidden = toggleCategoryVisibility(showAllCategories(), UNCATEGORISED, false);
    expect(filterCandidates(items, state({ hiddenCats: hidden })).map((c) => c.id)).toEqual([2]);
  });

  it("restores a category when it is switched back on", () => {
    const categories = [cat(1, "A"), cat(2, "B")];
    let hidden = toggleCategoryVisibility(showAllCategories(), "1", false);
    expect(allCategoriesOn(hidden, categories)).toBe(false);
    hidden = toggleCategoryVisibility(hidden, "1", true);
    expect(allCategoriesOn(hidden, categories)).toBe(true);
  });

  it("supports the all-categories toggle in both directions", () => {
    const categories = [cat(1, "A"), cat(2, "B")];
    const none = hideAllCategories(categories);
    expect(onCategoryCount(none, categories)).toBe(0);
    expect(filterCandidates([candidate(1, 1)], state({ hiddenCats: none }))).toHaveLength(0);

    const all = showAllCategories();
    expect(onCategoryCount(all, categories)).toBe(3);
    expect(filterCandidates([candidate(1, 1)], state({ hiddenCats: all }))).toHaveLength(1);
  });

  it("does not uncheck 'all categories' just because a category was added", () => {
    const hidden = showAllCategories();
    expect(allCategoriesOn(hidden, [cat(1, "A")])).toBe(true);
    expect(allCategoriesOn(hidden, [cat(1, "A"), cat(2, "New")])).toBe(true);
  });
});

describe("other filters", () => {
  it("applies tag, mark, search and date filters", () => {
    const items = [candidate(1, null), candidate(2, null)];
    items[0].tag_slug = "high-priority";
    items[1].important = true;
    items[1].topic = "Qwen serving";

    expect(
      filterCandidates(items, state({ tagFilters: new Set(["high-priority"]) })).map((c) => c.id),
    ).toEqual([1]);
    expect(
      filterCandidates(items, state({ markFilters: new Set(["important"]) })).map((c) => c.id),
    ).toEqual([2]);
    expect(filterCandidates(items, state({ search: "qwen" })).map((c) => c.id)).toEqual([2]);
    expect(filterCandidates(items, state({ dateFrom: "2026-09-01" }))).toHaveLength(0);
    expect(filterCandidates(items, state({ dateTo: "2026-01-01" }))).toHaveLength(0);
  });

  it("distinguishes an active filter from an empty corpus", () => {
    const categories = [cat(1, "A")];
    expect(filtersAreDefault(state(), categories)).toBe(true);
    expect(filtersAreDefault(state({ search: "qwen" }), categories)).toBe(false);
    expect(
      filtersAreDefault(state({ hiddenCats: hideAllCategories(categories) }), categories),
    ).toBe(false);
  });
});

describe("marked tab", () => {
  function marked(): Candidate[] {
    const a = candidate(1, 1);
    a.important = true;
    a.marked_at = "2026-08-17T09:00:00+00:00";
    a.notes = "ask about routing";

    const b = candidate(2, 2);
    b.shortlisted = true;
    b.marked_at = "2026-08-19T09:00:00+00:00";

    const c = candidate(3, 1);
    c.important = true;
    c.shortlisted = true;
    c.marked_at = "2026-08-18T09:00:00+00:00";

    return [a, b, c, candidate(4, 1)];
  }

  it("keeps only marked items, newest mark first", () => {
    const rows = filterMarkedCandidates(marked(), {
      view: "all",
      hiddenCats: showAllCategories(),
    });
    expect(rows.map((c) => c.id)).toEqual([2, 3, 1]);
  });

  it("separates important from shortlisted", () => {
    const items = marked();
    const important = filterMarkedCandidates(items, {
      view: "important",
      hiddenCats: showAllCategories(),
    });
    const shortlist = filterMarkedCandidates(items, {
      view: "shortlist",
      hiddenCats: showAllCategories(),
    });
    expect(important.map((c) => c.id)).toEqual([3, 1]);
    expect(shortlist.map((c) => c.id)).toEqual([2, 3]);
  });

  it("filters by category and searches comments", () => {
    const items = marked();
    const hidden = toggleCategoryVisibility(showAllCategories(), "1", false);
    expect(
      filterMarkedCandidates(items, { view: "all", hiddenCats: hidden }).map((c) => c.id),
    ).toEqual([2]);
    expect(
      filterMarkedCandidates(items, {
        view: "all",
        hiddenCats: showAllCategories(),
        search: "routing",
      }).map((c) => c.id),
    ).toEqual([1]);
  });

  it("sorts items marked before dates were recorded last", () => {
    const items = marked();
    const legacy = candidate(9, 1);
    legacy.important = true;
    const rows = filterMarkedCandidates([legacy, ...items], {
      view: "all",
      hiddenCats: showAllCategories(),
    });
    expect(rows.map((c) => c.id)).toEqual([2, 3, 1, 9]);
  });
});
