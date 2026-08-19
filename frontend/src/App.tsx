import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type Candidate,
  type Category,
  type EmailDetail,
  type IdeaSearch,
  type IdeaSearchDetail,
  type Job,
  type PublishStatus,
  type SearchHit,
  type SearchPreview,
  type SettingsStatus,
  type Stats,
  type SyncPreview,
} from "./api";
import { MarkdownBody, MarkdownInline } from "./markdown";
import {
  UNCATEGORISED,
  allCategoriesOn,
  filterCandidates,
  filterMarkedCandidates,
  filtersAreDefault,
  hideAllCategories,
  isCategoryOn,
  isMarked,
  onCategoryCount,
  showAllCategories,
  toggleCategoryVisibility,
  type MarkFilter,
  type MarkView,
  type TagFilter,
} from "./filters";
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
  type HitView,
} from "./search";

const TAG_OPTIONS: { id: TagFilter; label: string }[] = [
  { id: "high-priority", label: "High priority" },
  { id: "strong", label: "Strong" },
  { id: "possible", label: "Possible" },
];

type TabId = "review" | "marked" | "search";

const TABS: { id: TabId; label: string; sub: string }[] = [
  {
    id: "review",
    label: "Important items extracted from emails",
    sub: "What GPT pulled out of each newsletter",
  },
  {
    id: "marked",
    label: "Review marked items",
    sub: "Everything you marked important or shortlisted",
  },
  {
    id: "search",
    label: "Search for ideas",
    sub: "Ask a question across a date range of emails",
  },
];

const MARK_OPTIONS: { id: MarkFilter; label: string }[] = [
  { id: "important", label: "Marked important by user" },
  { id: "shortlist", label: "Shortlisted by user" },
];

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function addDay(iso: string) {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

function num(p: Record<string, unknown>, key: string): number {
  const v = p[key];
  return typeof v === "number" ? v : Number(v) || 0;
}

function str(p: Record<string, unknown>, key: string): string {
  const v = p[key];
  return typeof v === "string" ? v : "";
}

function parseApiTime(iso: string): number {
  if (!iso) return NaN;
  const trimmed = iso.trim();
  if (/[zZ]$/.test(trimmed) || /[+-]\d{2}:?\d{2}$/.test(trimmed)) {
    return new Date(trimmed).getTime();
  }
  return new Date(`${trimmed}Z`).getTime();
}

function elapsed(fromIso: string, now: number) {
  const start = parseApiTime(fromIso);
  if (!Number.isFinite(start)) return "0s";
  const s = Math.max(0, Math.floor((now - start) / 1000));
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (m >= 60) {
    const h = Math.floor(m / 60);
    return `${h}h ${m % 60}m ${r}s`;
  }
  return m ? `${m}m ${r}s` : `${r}s`;
}

function formatMarkedDate(iso: string) {
  const ms = parseApiTime(iso);
  if (!Number.isFinite(ms)) return "";
  return new Date(ms).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function truncate(text: string, n = 80) {
  const t = text.trim();
  return t.length > n ? t.slice(0, n - 1) + "…" : t;
}

function remainingEstimate(current: number, total: number) {
  if (total <= 0) return "";
  const emailsLeft = current < 1 ? total : Math.max(0, total - current + 1);
  if (emailsLeft <= 0) return "";
  const lo = emailsLeft * 2;
  const hi = emailsLeft * 3;
  return lo === hi ? `About ${lo} min remaining` : `About ${lo}–${hi} min remaining`;
}

function toggleInSet<T>(set: Set<T>, value: T): Set<T> {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

function NewCategoryForm({
  onSave,
  onCancel,
}: {
  onSave: (name: string) => Promise<unknown>;
  onCancel?: () => void;
}) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="new-cat-form"
      onSubmit={async (e) => {
        e.preventDefault();
        const trimmed = name.trim();
        if (!trimmed || busy) return;
        setBusy(true);
        try {
          await onSave(trimmed);
          setName("");
        } finally {
          setBusy(false);
        }
      }}
    >
      <input
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="New category name"
        disabled={busy}
        aria-label="New category name"
      />
      <button type="submit" disabled={busy || !name.trim()}>
        Add
      </button>
      {onCancel && (
        <button type="button" className="btn-quiet" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      )}
    </form>
  );
}

function CommentBox({
  value,
  onSave,
  onCancel,
}: {
  value: string;
  onSave: (text: string) => Promise<unknown>;
  onCancel: () => void;
}) {
  const [text, setText] = useState(value);
  const [busy, setBusy] = useState(false);

  async function save() {
    if (busy) return;
    setBusy(true);
    try {
      await onSave(text.trim());
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="comment-form"
      onSubmit={(e) => {
        e.preventDefault();
        save();
      }}
    >
      <textarea
        autoFocus
        rows={2}
        value={text}
        disabled={busy}
        placeholder="Why is this worth a probe? (optional)"
        aria-label="Your comment"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") onCancel();
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save();
        }}
      />
      <div className="comment-form-actions">
        <button type="submit" disabled={busy}>
          Save comment
        </button>
        <button type="button" className="btn-quiet" onClick={onCancel} disabled={busy}>
          {value ? "Cancel" : "Skip"}
        </button>
      </div>
    </form>
  );
}

/** Category dropdown that can also create a category on the spot. */
function CategoryPicker({
  c,
  categories,
  onPatch,
  onAddCategory,
}: {
  c: Candidate;
  categories: Category[];
  onPatch: (id: number, body: Record<string, unknown>) => Promise<boolean>;
  onAddCategory: (name: string) => Promise<Category>;
}) {
  const [adding, setAdding] = useState(false);

  if (adding) {
    return (
      <NewCategoryForm
        onSave={async (name) => {
          try {
            const cat = await onAddCategory(name);
            await onPatch(c.id, { category_id: cat.id });
            setAdding(false);
          } catch {
            // The message is already on screen; keep the form open to retry.
          }
        }}
        onCancel={() => setAdding(false)}
      />
    );
  }
  return (
    <select
      value={c.category_id ?? ""}
      aria-label="Category"
      onChange={async (e) => {
        if (e.target.value === "__new__") {
          setAdding(true);
          return;
        }
        if (!e.target.value) await onPatch(c.id, { clear_category: true });
        else await onPatch(c.id, { category_id: Number(e.target.value) });
      }}
    >
      <option value="">Categorise…</option>
      {categories.map((cat) => (
        <option key={cat.id} value={cat.id}>
          {cat.name}
        </option>
      ))}
      <option value="__new__">+ Add new category…</option>
    </select>
  );
}

/** The saved comment, with a way into the editor. */
function CommentDisplay({ c, onEdit }: { c: Candidate; onEdit: () => void }) {
  if (c.notes) {
    return (
      <div className="comment">
        <p className="comment-text">{c.notes}</p>
        <button type="button" className="linkish" onClick={onEdit}>
          Edit comment
        </button>
      </div>
    );
  }
  if (!isMarked(c)) return null;
  return (
    <button type="button" className="linkish add-comment" onClick={onEdit}>
      Add a comment
    </button>
  );
}

/**
 * Comments are collected in a dialog rather than on the card, because marking an
 * item can move its card into the collapsed "Processed by you" section straight
 * away, which would take an inline editor with it.
 */
function CommentPrompt({
  c,
  categories,
  onPatch,
  onAddCategory,
  onSave,
  onClose,
}: {
  c: Candidate;
  categories: Category[];
  onPatch: (id: number, body: Record<string, unknown>) => Promise<boolean>;
  onAddCategory: (name: string) => Promise<Category>;
  onSave: (text: string) => Promise<unknown>;
  onClose: () => void;
}) {
  return (
    <>
      <div className="email-backdrop" onClick={onClose} />
      <div className="comment-modal">
        <h2>{c.notes ? "Edit your comment" : "Add a comment"}</h2>
        <p className="meta">{c.topic}</p>

        {/* The category saves on its own, so the reminder still works if the
            comment is skipped. */}
        <div className={`prompt-category ${c.category_id ? "" : "missing"}`}>
          {c.category_id ? (
            <span className="prompt-category-label">Category</span>
          ) : (
            <span className="prompt-category-label">You forgot to add a category</span>
          )}
          <CategoryPicker
            c={c}
            categories={categories}
            onPatch={onPatch}
            onAddCategory={onAddCategory}
          />
        </div>

        <CommentBox value={c.notes} onSave={onSave} onCancel={onClose} />
      </div>
    </>
  );
}

function CheckMenu({
  id,
  label,
  summary,
  openId,
  setOpenId,
  children,
}: {
  id: string;
  label: string;
  summary?: string;
  openId: string | null;
  setOpenId: (id: string | null) => void;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const open = openId === id;
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpenId(null);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open, setOpenId]);
  return (
    <div className="check-menu" ref={ref}>
      <button
        type="button"
        className={`menu-btn ${open ? "open" : ""} ${summary ? "has-filters" : ""}`}
        onClick={() => setOpenId(open ? null : id)}
        aria-expanded={open}
      >
        {label}
        {summary ? ` · ${summary}` : ""}
      </button>
      {open && <div className="menu-panel">{children}</div>}
    </div>
  );
}

export default function App() {
  const [, setStats] = useState<Stats | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [settings, setSettings] = useState<SettingsStatus | null>(null);
  const [view, setView] = useState<TabId>("review");
  const [unprocessedOnly, setUnprocessedOnly] = useState(true);
  const [tagFilters, setTagFilters] = useState<Set<TagFilter>>(new Set());
  const [markFilters, setMarkFilters] = useState<Set<MarkFilter>>(new Set());
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [hiddenCats, setHiddenCats] = useState<Set<string>>(() => showAllCategories());
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [dismissedJobId, setDismissedJobId] = useState<number | null>(null);
  const [commentFor, setCommentFor] = useState<number | null>(null);
  const [email, setEmail] = useState<EmailDetail | null>(null);
  const [emailExcerpt, setEmailExcerpt] = useState("");
  const [emailLoading, setEmailLoading] = useState(false);
  const [syncFrom, setSyncFrom] = useState("");
  const [syncTo, setSyncTo] = useState(todayIso());
  const [now, setNow] = useState(Date.now());
  const [syncConfirm, setSyncConfirm] = useState<SyncPreview | null>(null);
  const [publishStatus, setPublishStatus] = useState<PublishStatus>({
    status: "idle",
    url: "",
    error: "",
  });
  const lastProgressLoad = useRef("");

  const load = useCallback(async () => {
    const [s, cats, cands] = await Promise.all([
      api.stats(),
      api.categories(),
      api.candidates({ status: "all" }),
    ]);
    setStats(s);
    setCategories(cats);
    setCandidates(cands);
    setSyncFrom((prev) => prev || (s.date_to ? addDay(s.date_to) : todayIso()));
    try {
      setSettings(await api.settings());
    } catch (e) {
      setError((e as Error).message);
    }
    try {
      const active = await api.activeJob();
      if (active && (active.status === "queued" || active.status === "running")) {
        setJob((prev) => prev ?? active);
      }
    } catch {
      /* ignore */
    }
  }, []);

  const openEmail = useCallback(async (id: number, excerpt: string) => {
    setEmailExcerpt(excerpt);
    setEmailLoading(true);
    setEmail(null);
    try {
      setEmail(await api.email(id));
    } catch (e) {
      setError((e as Error).message);
      setEmailExcerpt("");
    } finally {
      setEmailLoading(false);
    }
  }, []);

  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const gmail = q.get("gmail");
    if (!gmail) return;
    if (gmail === "error") setError(q.get("detail") || "Gmail connect failed.");
    window.history.replaceState({}, "", window.location.pathname);
    api
      .settings()
      .then(setSettings)
      .catch((e: Error) => setError(e.message));
  }, []);

  const jobBusy = !!job && job.status !== "done" && job.status !== "failed";

  async function startSync(overwrite: boolean) {
    setSyncConfirm(null);
    setError("");
    setDismissedJobId(null);
    lastProgressLoad.current = "";
    setJob(
      await api.sync({
        date_from: syncFrom || undefined,
        date_to: syncTo || undefined,
        extract: true,
        overwrite_extracted: overwrite,
      }),
    );
  }

  async function requestSync() {
    setError("");
    setDismissedJobId(null);
    if (!settings?.connected) {
      setError("Connect Gmail first.");
      return;
    }
    try {
      const preview = await api.syncPreview({
        date_from: syncFrom || undefined,
        date_to: syncTo || undefined,
      });
      if (preview.needs_confirm) {
        setSyncConfirm(preview);
        return;
      }
      await startSync(false);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    if (!jobBusy) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [jobBusy]);

  useEffect(() => {
    if (!jobBusy || !job) return;
    const jobId = job.id;
    const t = setInterval(async () => {
      try {
        const next = await api.job(jobId);
        setJob(next);
        const p = next.progress || {};
        const key = [
          next.status,
          str(p, "phase"),
          num(p, "extracted") || num(p, "extract_extracted"),
          num(p, "empty") || num(p, "extract_empty"),
          num(p, "new_emails"),
        ].join(":");
        if (next.status === "done" || next.status === "failed") {
          load();
          return;
        }
        if (key !== lastProgressLoad.current) {
          lastProgressLoad.current = key;
          const phase = str(p, "phase");
          if (
            phase === "fetched" ||
            phase === "extracting" ||
            phase === "done" ||
            num(p, "extracted") ||
            num(p, "extract_extracted")
          ) {
            load().catch(() => undefined);
          }
        }
      } catch {
        /* ignore poll errors */
      }
    }, 1500);
    return () => clearInterval(t);
  }, [jobBusy, job?.id, load]);

  // Poll publish status while a publish is running.
  useEffect(() => {
    if (publishStatus.status !== "running") return;
    const t = setInterval(() => {
      api
        .publishStatus()
        .then(setPublishStatus)
        .catch(() => undefined);
    }, 2000);
    return () => clearInterval(t);
  }, [publishStatus.status]);

  async function startPublish() {
    try {
      const s = await api.publish();
      setPublishStatus(s);
    } catch (e) {
      setPublishStatus({ status: "error", url: "", error: (e as Error).message });
    }
  }

  /** Returns false if the change did not stick, so callers do not act on it. */
  async function patch(id: number, body: Record<string, unknown>): Promise<boolean> {
    try {
      const updated = await api.patchCandidate(id, body);
      setCandidates((prev) => prev.map((c) => (c.id === id ? updated : c)));
      setStats(await api.stats());
      setError("");
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    }
  }

  async function addCategory(name: string) {
    try {
      const cat = await api.addCategory(name);
      setCategories((prev) => {
        if (prev.some((c) => c.id === cat.id)) return prev;
        return [...prev, cat].sort(
          (a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name),
        );
      });
      return cat;
    } catch (e) {
      setError((e as Error).message);
      throw e;
    }
  }

  const visible = useMemo(
    () =>
      filterCandidates(candidates, {
        tagFilters,
        markFilters,
        search,
        dateFrom,
        dateTo,
        hiddenCats,
      }),
    [candidates, tagFilters, markFilters, search, dateFrom, dateTo, hiddenCats],
  );

  const hideProcessedInMain = unprocessedOnly && markFilters.size === 0;
  const mainCards = hideProcessedInMain ? visible.filter((c) => !c.processed) : visible;
  const processedCards = hideProcessedInMain ? visible.filter((c) => c.processed) : [];

  const showJob = job && job.id !== dismissedJobId;
  const markedCount = useMemo(() => candidates.filter(isMarked).length, [candidates]);
  const commentCandidate = commentFor
    ? candidates.find((c) => c.id === commentFor) ?? null
    : null;

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>AI News Newsletter Explorer</h1>
        </div>
        <div className="header-right">
          <PublishControl status={publishStatus} onPublish={startPublish} />
          <GmailControl settings={settings} onChange={setSettings} setError={setError} />
        </div>
      </header>

      <nav className="tabs" role="tablist" aria-label="Sections">
        {TABS.map((tab) => {
          const count = tab.id === "marked" ? markedCount : 0;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={view === tab.id}
              className={`tab ${view === tab.id ? "on" : ""}`}
              onClick={() => {
                setOpenMenu(null);
                setView(tab.id);
              }}
            >
              <span className="tab-label">
                {tab.label}
                {count ? <span className="tab-count">{count}</span> : null}
              </span>
              <span className="tab-sub">{tab.sub}</span>
            </button>
          );
        })}
      </nav>

      {view === "search" ? (
        <SearchView
          onOpenEmail={openEmail}
          setError={setError}
          error={error}
          categories={categories}
          onAddCategory={addCategory}
          onKept={(cand) => {
            setCandidates((prev) => {
              if (prev.some((c) => c.id === cand.id)) {
                return prev.map((c) => (c.id === cand.id ? cand : c));
              }
              return [cand, ...prev];
            });
            api.stats().then(setStats).catch(() => undefined);
          }}
        />
      ) : view === "marked" ? (
        <MarkedView
          candidates={candidates}
          categories={categories}
          error={error}
          onPatch={patch}
          onAddCategory={addCategory}
          onOpenEmail={openEmail}
          openMenu={openMenu}
          setOpenMenu={setOpenMenu}
        />
      ) : (
        <>
          <JobPanel
            settings={settings}
            job={showJob ? job : null}
            busy={jobBusy || !!syncConfirm}
            error={error}
            syncFrom={syncFrom}
            syncTo={syncTo}
            now={now}
            onSyncFrom={setSyncFrom}
            onSyncTo={setSyncTo}
            onSync={async () => {
              try {
                await requestSync();
              } catch (e) {
                setError((e as Error).message);
              }
            }}
            onDismiss={() => job && setDismissedJobId(job.id)}
          />

          <div className="filter-bar">
            <CheckMenu
              id="filters"
              label="Filters"
              summary={
                tagFilters.size + markFilters.size
                  ? String(tagFilters.size + markFilters.size)
                  : undefined
              }
              openId={openMenu}
              setOpenId={setOpenMenu}
            >
              <p className="menu-heading">Model ranking</p>
              {TAG_OPTIONS.map((opt) => (
                <label key={opt.id} className="menu-check">
                  <input
                    type="checkbox"
                    checked={tagFilters.has(opt.id)}
                    onChange={() => setTagFilters((prev) => toggleInSet(prev, opt.id))}
                  />
                  {opt.label}
                </label>
              ))}
              <p className="menu-heading">Your marks</p>
              {MARK_OPTIONS.map((opt) => (
                <label key={opt.id} className="menu-check">
                  <input
                    type="checkbox"
                    checked={markFilters.has(opt.id)}
                    onChange={() => setMarkFilters((prev) => toggleInSet(prev, opt.id))}
                  />
                  {opt.label}
                </label>
              ))}
            </CheckMenu>
            <CheckMenu
              id="categories"
              label="Categories"
              summary={
                allCategoriesOn(hiddenCats, categories)
                  ? undefined
                  : String(onCategoryCount(hiddenCats, categories))
              }
              openId={openMenu}
              setOpenId={setOpenMenu}
            >
              <label className="menu-check">
                <input
                  type="checkbox"
                  checked={allCategoriesOn(hiddenCats, categories)}
                  onChange={(e) =>
                    setHiddenCats(
                      e.target.checked ? showAllCategories() : hideAllCategories(categories),
                    )
                  }
                />
                All categories
              </label>
              <label className="menu-check">
                <input
                  type="checkbox"
                  checked={isCategoryOn(hiddenCats, UNCATEGORISED)}
                  onChange={(e) =>
                    setHiddenCats((prev) =>
                      toggleCategoryVisibility(prev, UNCATEGORISED, e.target.checked),
                    )
                  }
                />
                Uncategorised
              </label>
              {categories.map((cat) => (
                <label key={cat.id} className="menu-check">
                  <input
                    type="checkbox"
                    checked={isCategoryOn(hiddenCats, String(cat.id))}
                    onChange={(e) =>
                      setHiddenCats((prev) =>
                        toggleCategoryVisibility(prev, String(cat.id), e.target.checked),
                      )
                    }
                  />
                  {cat.name}
                </label>
              ))}
              <NewCategoryForm onSave={addCategory} />
            </CheckMenu>
            <label className="unprocessed-toggle">
              <input
                type="checkbox"
                checked={unprocessedOnly}
                onChange={(e) => setUnprocessedOnly(e.target.checked)}
              />
              Show unprocessed items only
            </label>
            <input
              type="search"
              placeholder="Search topic, idea, excerpt, title…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <label className="date-mini">
              From
              <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            </label>
            <label className="date-mini">
              To
              <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            </label>
            <button
              type="button"
              className="btn-quiet"
              onClick={() => {
                setUnprocessedOnly(true);
                setTagFilters(new Set());
                setMarkFilters(new Set());
                setSearch("");
                setDateFrom("");
                setDateTo("");
                setHiddenCats(showAllCategories());
              }}
            >
              Clear
            </button>
            <span className="filter-count">{mainCards.length} shown</span>
          </div>

          {processedCards.length > 0 && (
            <details className="processed-panel">
              <summary>
                <span>Processed by you ({processedCards.length})</span>
                <span className="processed-hint">
                  Marked important by user or shortlisted by user
                </span>
              </summary>
              <div id="processed-list">
                {processedCards.map((c) => (
                  <CandidateCard
                    key={c.id}
                    c={c}
                    categories={categories}
                    onPatch={patch}
                    onAddCategory={addCategory}
                    onOpenEmail={openEmail}
                    onComment={setCommentFor}
                  />
                ))}
              </div>
            </details>
          )}

          <p className="section-label">{unprocessedOnly && markFilters.size === 0 ? "Unprocessed queue" : "Queue"}</p>
          <main id="candidate-list">
            {mainCards.length === 0 ? (
              <div className="empty-queue">
                {filtersAreDefault(
                  { tagFilters, markFilters, search, dateFrom, dateTo, hiddenCats },
                  categories,
                )
                  ? "No unprocessed candidates. Sync Gmail for a date range to pull new newsletters."
                  : "No candidates match these filters."}
              </div>
            ) : (
              mainCards.map((c) => (
                <CandidateCard
                  key={c.id}
                  c={c}
                  categories={categories}
                  onPatch={patch}
                  onAddCategory={addCategory}
                  onOpenEmail={openEmail}
                  onComment={setCommentFor}
                />
            ))
          )}
          </main>
        </>
      )}

      {commentCandidate && (
        <CommentPrompt
          c={commentCandidate}
          categories={categories}
          onPatch={patch}
          onAddCategory={addCategory}
          onSave={async (text) => {
            // Keep the editor open on failure so the comment is not lost.
            if (text === commentCandidate.notes) setCommentFor(null);
            else if (await patch(commentCandidate.id, { notes: text })) setCommentFor(null);
          }}
          onClose={() => setCommentFor(null)}
        />
      )}

      {syncConfirm && (
        <SyncConfirm
          preview={syncConfirm}
          onSkip={() => startSync(false).catch((e: Error) => setError(e.message))}
          onOverwrite={() => startSync(true).catch((e: Error) => setError(e.message))}
          onCancel={() => setSyncConfirm(null)}
        />
      )}

      {(email || emailLoading) && (
        <>
          <div
            className="email-backdrop"
            onClick={() => {
              setEmail(null);
              setEmailExcerpt("");
              setEmailLoading(false);
            }}
          />
          <div className="email-modal">
            <div className="email-modal-bar">
              <button
                type="button"
                className="modal-close"
                onClick={() => {
                  setEmail(null);
                  setEmailExcerpt("");
                  setEmailLoading(false);
                }}
              >
                Close
              </button>
            </div>
            {emailLoading && !email ? (
              <p className="meta">Loading email…</p>
            ) : email ? (
              <MarkdownBody text={email.body_md} highlight={emailExcerpt} />
            ) : null}
          </div>
        </>
      )}
    </div>
  );
}

function SyncConfirm({
  preview,
  onSkip,
  onOverwrite,
  onCancel,
}: {
  preview: SyncPreview;
  onSkip: () => void;
  onOverwrite: () => void;
  onCancel: () => void;
}) {
  const range =
    preview.date_from && preview.date_to
      ? `${preview.date_from} – ${preview.date_to}`
      : preview.date_from
        ? `from ${preview.date_from}`
        : preview.date_to
          ? `through ${preview.date_to}`
          : "this date range";
  return (
    <>
      <div className="email-backdrop" onClick={onCancel} />
      <div className="confirm-modal" role="dialog" aria-labelledby="sync-confirm-title">
        <h2 id="sync-confirm-title">Already extracted</h2>
        <p>
          {range} already has <strong>{preview.extracted}</strong> newsletter
          {preview.extracted === 1 ? "" : "s"} that GPT has processed
          {preview.candidates
            ? ` (${preview.candidates} probe idea${preview.candidates === 1 ? "" : "s"})`
            : ""}
          . Sync will still check Gmail for anything new.
        </p>
        {preview.pending > 0 && (
          <p>
            {preview.pending} email{preview.pending === 1 ? "" : "s"} in this range still need extraction
            and will be processed either way.
          </p>
        )}
        {preview.marked > 0 && (
          <p className="warn">
            {preview.marked} idea{preview.marked === 1 ? "" : "s"} in this range{" "}
            {preview.marked === 1 ? "is" : "are"} marked important, shortlisted, or have notes.
            Overwriting will delete those marks.
          </p>
        )}
        <div className="confirm-actions">
          <button type="button" className="btn-primary" onClick={onSkip}>
            Skip already extracted
          </button>
          <button type="button" className="btn-danger-quiet" onClick={onOverwrite}>
            Overwrite earlier extractions
          </button>
          <button type="button" className="btn-quiet" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </div>
    </>
  );
}

function JobPanel({
  settings,
  job,
  busy,
  error,
  syncFrom,
  syncTo,
  now,
  onSyncFrom,
  onSyncTo,
  onSync,
  onDismiss,
}: {
  settings: SettingsStatus | null;
  job: Job | null;
  busy: boolean;
  error: string;
  syncFrom: string;
  syncTo: string;
  now: number;
  onSyncFrom: (v: string) => void;
  onSyncTo: (v: string) => void;
  onSync: () => void;
  onDismiss: () => void;
}) {
  return (
    <section className="job-panel">
      <div className="job-row">
        <label>
          From
          <input type="date" value={syncFrom} onChange={(e) => onSyncFrom(e.target.value)} disabled={busy} />
        </label>
        <label>
          To
          <input type="date" value={syncTo} onChange={(e) => onSyncTo(e.target.value)} disabled={busy} />
        </label>
        <button type="button" className="btn-primary" disabled={busy} onClick={onSync}>
          Sync Gmail
        </button>
      </div>
      {!job && (
        <p className="job-idle">
          {settings?.connected
            ? `Gmail connected as ${settings.email || "you"}. Sync downloads that date range, then GPT-5.4 reads each new newsletter and extracts probe ideas (about 2–3 minutes per email).`
            : settings?.has_client
              ? "Click Connect Gmail in the header, then sync a date range."
              : "Add GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET to .env, restart, then connect Gmail."}
        </p>
      )}
      {error && <p className="err">{error}</p>}
      {job && <JobProgress job={job} now={now} onDismiss={onDismiss} />}
    </section>
  );
}

function JobProgress({ job, now, onDismiss }: { job: Job; now: number; onDismiss: () => void }) {
  const p = job.progress || {};
  const phase = str(p, "phase") || job.status;
  const listed = num(p, "listed");
  const current = num(p, "current");
  const total = num(p, "total");
  const newEmails = num(p, "new_emails");
  const skipped = num(p, "skipped");
  const extracted = num(p, "extracted") || num(p, "extract_extracted");
  const failed = num(p, "failed") || num(p, "extract_failed");
  const empty = num(p, "empty") || num(p, "extract_empty");
  const ideasThisEmail = num(p, "ideas_this_email");
  const alreadyExtracted = num(p, "already_extracted") || num(p, "skipped_extracted");
  const extractSkipped = num(p, "extract_skipped");
  const overwrite =
    Boolean(p.overwrite) || Boolean(job.payload?.overwrite_extracted);
  const subject = str(p, "subject");
  const running = job.status === "queued" || job.status === "running";
  const isSync = job.kind === "sync";
  const downloading = phase === "listing" || phase === "fetching" || phase === "fetched";
  const extracting = phase === "extracting";

  let title = "Working…";
  let detail = "";
  let hint = "";
  let pct = 0;
  let determinate = false;

  if (job.status === "failed") {
    title = job.kind === "extract" ? "Extraction failed" : "Sync failed";
    detail = job.error || "Something went wrong.";
  } else if (phase === "listing") {
    title = isSync ? "Step 1 of 2: Finding emails in Gmail" : "Finding emails in Gmail";
    detail = "Searching the AINews label for this date range.";
    hint = "Download is usually quick. The slow part is next: GPT reads each new newsletter and extracts probe ideas.";
  } else if (phase === "fetching") {
    title = listed
      ? `Step 1 of 2: Downloading ${current} of ${listed} from Gmail`
      : "Step 1 of 2: Downloading emails from Gmail";
    detail = `${newEmails} new, ${skipped} already stored.`;
    hint = overwrite
      ? "After download, GPT will re-extract this range and replace earlier probe ideas."
      : "After download, GPT extracts new or pending emails only. Already extracted newsletters are skipped.";
    determinate = listed > 0;
    pct = listed ? Math.min(100, (current / listed) * 100) : 0;
  } else if (phase === "fetched") {
    title = "Step 1 of 2: Download complete";
    detail = `${listed} in range. ${newEmails} new, ${skipped} already stored.`;
    hint =
      newEmails > 0
        ? `Starting idea extraction for ${newEmails} new email${newEmails === 1 ? "" : "s"}.`
        : "No new emails to process.";
    determinate = true;
    pct = 100;
  } else if (phase === "extracting") {
    const n = current || 0;
    const of = total || newEmails || 0;
    const verb = overwrite ? "Re-extracting" : "Extracting";
    title = isSync
      ? of
        ? `Step 2 of 2: ${verb} probe ideas — ${n} of ${of}`
        : `Step 2 of 2: ${verb} probe ideas`
      : of
        ? `${verb} probe ideas — ${n} of ${of}`
        : `${verb} probe ideas`;
    detail = subject
      ? overwrite
        ? `GPT-5.4 is re-reading “${truncate(subject, 90)}” and replacing earlier probe ideas.`
        : `GPT-5.4 is reading “${truncate(subject, 90)}” and pulling out probe ideas.`
      : overwrite
        ? "GPT-5.4 is re-reading newsletters and replacing earlier probe ideas."
        : "GPT-5.4 is reading each newsletter and pulling out probe ideas.";
    const eta = remainingEstimate(n, of);
    hint = [
      overwrite
        ? "Overwrite is on. Previous ideas for these emails will be replaced."
        : "This is the slow part — about 2–3 minutes per email with high reasoning.",
      eta,
      extracted ? `${extracted} newsletter${extracted === 1 ? "" : "s"} already yielded ideas.` : "",
      ideasThisEmail ? `Last email: ${ideasThisEmail} idea${ideasThisEmail === 1 ? "" : "s"}.` : "",
      "You can keep reviewing while this runs.",
    ]
      .filter(Boolean)
      .join(" ");
    determinate = of > 0;
    pct = of ? Math.min(100, (Math.max(n - 0.15, 0) / of) * 100) : 0;
  } else if (job.status === "done") {
    title = job.kind === "extract" ? "Extraction complete" : "Sync complete";
    const skippedExtracted = alreadyExtracted || (extracted === 0 ? extractSkipped : 0);
    if (newEmails === 0 && extracted === 0 && skippedExtracted > 0 && !overwrite) {
      title = "Already extracted";
      detail = `No new emails. ${skippedExtracted} newsletter${skippedExtracted === 1 ? " was" : "s were"} already processed — GPT was not re-run.`;
    } else {
      const parts = [];
      if (listed) parts.push(`${listed} emails in range`);
      if (newEmails || skipped) parts.push(`${newEmails} new, ${skipped} already stored`);
      if (overwrite && extracted) {
        parts.push(`Re-extracted ideas from ${extracted} email${extracted === 1 ? "" : "s"}`);
      } else if (extracted) {
        parts.push(`Extracted ideas from ${extracted} email${extracted === 1 ? "" : "s"}`);
      } else {
        parts.push("No new ideas extracted");
      }
      if (!overwrite && skippedExtracted) {
        parts.push(`skipped ${skippedExtracted} already extracted`);
      }
      if (empty) parts.push(`${empty} with no probes`);
      if (failed) parts.push(`${failed} failed`);
      detail = parts.join(". ") + ".";
    }
    determinate = true;
    pct = 100;
  }

  const downloadState = !isSync
    ? "hidden"
    : job.status === "done" || extracting
      ? "done"
      : downloading
        ? "active"
        : "pending";
  const extractState =
    job.status === "done"
      ? "done"
      : extracting || job.kind === "extract"
        ? "active"
        : "pending";

  return (
    <div className={`job-progress ${job.status}`}>
      {running && (
        <ol className="job-steps" aria-label="Sync stages">
          {downloadState !== "hidden" && (
            <li className={downloadState}>
              <span className="step-n">1</span>
              Download from Gmail
            </li>
          )}
          <li className={extractState}>
            <span className="step-n">{downloadState === "hidden" ? "1" : "2"}</span>
            Extract probe ideas
          </li>
        </ol>
      )}
      <h2>{title}</h2>
      <p className="detail">
        {detail}
        {running ? ` · ${elapsed(job.created_at, now)} elapsed` : ""}
      </p>
      {running && hint && <p className="job-hint">{hint}</p>}
      {running && (
        <div className="progress-track" aria-hidden="true">
          <div
            className={`progress-fill ${determinate ? "" : "indeterminate"}`}
            style={determinate ? { width: `${pct}%` } : undefined}
          />
        </div>
      )}
      {!running && (
        <button type="button" className="btn-quiet" onClick={onDismiss}>
          Dismiss
        </button>
      )}
    </div>
  );
}

function CandidateCard({
  c,
  categories,
  onPatch,
  onAddCategory,
  onOpenEmail,
  onComment,
}: {
  c: Candidate;
  categories: Category[];
  onPatch: (id: number, body: Record<string, unknown>) => Promise<boolean>;
  onAddCategory: (name: string) => Promise<Category>;
  onOpenEmail: (id: number, excerpt: string) => void;
  onComment: (id: number) => void;
}) {
  // Marking is one click; the comment prompt opens afterwards so it stays optional.
  async function toggleMark(field: "important" | "shortlisted") {
    const turningOn = !c[field];
    const ok = await onPatch(c.id, { [field]: turningOn });
    if (ok && turningOn) onComment(c.id);
  }

  const cls = [
    "candidate-card",
    c.important ? "is-important" : "",
    c.shortlisted ? "is-shortlisted" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <article className={cls}>
      <div className="card-top">
        <div>
          <span className={`badge ${c.tag_slug}`}>{c.tag}</span>
          {c.important && <span className="badge important-flag">Marked important by user</span>}
          {c.shortlisted && <span className="badge shortlist-flag">Shortlisted by user</span>}
        </div>
        <div className="card-actions">
          <CategoryPicker
            c={c}
            categories={categories}
            onPatch={onPatch}
            onAddCategory={onAddCategory}
          />
          <button
            type="button"
            className={`btn-important ${c.important ? "is-on" : ""}`}
            onClick={() => toggleMark("important")}
          >
            {c.important ? "Unmark Important" : "Mark Important"}
          </button>
          <button
            type="button"
            className={`btn-shortlist ${c.shortlisted ? "is-on" : ""}`}
            onClick={() => toggleMark("shortlisted")}
          >
            {c.shortlisted ? "Remove from Shortlist" : "Shortlist for Probe"}
          </button>
          <button
            type="button"
            className="btn-delete"
            onClick={() => {
              if (window.confirm("Delete this item? This cannot be undone.")) {
                onPatch(c.id, { deleted: true });
              }
            }}
          >
            Delete
          </button>
        </div>
      </div>
      <h2>{c.topic}</h2>
      <p className="meta">
        {c.email_date || c.date_iso} ·{" "}
        <button type="button" className="linkish" onClick={() => onOpenEmail(c.email_id, c.excerpt)}>
          {c.email_title}
        </button>
      </p>
      <p className="idea">{c.main_idea}</p>
      <blockquote className="excerpt">
        <MarkdownInline text={c.excerpt} />
      </blockquote>
      <CommentDisplay c={c} onEdit={() => onComment(c.id)} />
    </article>
  );
}

function MarkedRow({
  c,
  categories,
  onPatch,
  onAddCategory,
  onOpenEmail,
}: {
  c: Candidate;
  categories: Category[];
  onPatch: (id: number, body: Record<string, unknown>) => Promise<boolean>;
  onAddCategory: (name: string) => Promise<Category>;
  onOpenEmail: (id: number, excerpt: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const added = formatMarkedDate(c.marked_at);
  return (
    <article className="marked-row">
      <div className="card-top">
        <div>
          {c.important && <span className="badge important-flag">Important</span>}
          {c.shortlisted && <span className="badge shortlist-flag">Shortlisted</span>}
          <span className="badge cat-flag">{c.category_name || "Uncategorised"}</span>
        </div>
        <span className="marked-date">{added ? `Added ${added}` : "Date not recorded"}</span>
      </div>
      <h2>{c.topic}</h2>
      <p className="meta">
        {c.email_date || c.date_iso} ·{" "}
        <button type="button" className="linkish" onClick={() => onOpenEmail(c.email_id, c.excerpt)}>
          {c.email_title}
        </button>
      </p>
      <p className="idea">{c.main_idea}</p>
      {editing ? (
        <CommentBox
          value={c.notes}
          onSave={async (text) => {
            if (text === c.notes) setEditing(false);
            else if (await onPatch(c.id, { notes: text })) setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <CommentDisplay c={c} onEdit={() => setEditing(true)} />
      )}
      <div className="marked-actions">
        <CategoryPicker
          c={c}
          categories={categories}
          onPatch={onPatch}
          onAddCategory={onAddCategory}
        />
        <button
          type="button"
          className={`btn-important ${c.important ? "is-on" : ""}`}
          onClick={() => onPatch(c.id, { important: !c.important })}
        >
          {c.important ? "Unmark Important" : "Mark Important"}
        </button>
        <button
          type="button"
          className={`btn-shortlist ${c.shortlisted ? "is-on" : ""}`}
          onClick={() => onPatch(c.id, { shortlisted: !c.shortlisted })}
        >
          {c.shortlisted ? "Remove from Shortlist" : "Shortlist for Probe"}
        </button>
      </div>
    </article>
  );
}

const MARK_VIEWS: { id: MarkView; label: string }[] = [
  { id: "all", label: "All marked" },
  { id: "important", label: "Important only" },
  { id: "shortlist", label: "Shortlisted only" },
];

function MarkedView({
  candidates,
  categories,
  error,
  onPatch,
  onAddCategory,
  onOpenEmail,
  openMenu,
  setOpenMenu,
}: {
  candidates: Candidate[];
  categories: Category[];
  error: string;
  onPatch: (id: number, body: Record<string, unknown>) => Promise<boolean>;
  onAddCategory: (name: string) => Promise<Category>;
  onOpenEmail: (id: number, excerpt: string) => void;
  openMenu: string | null;
  setOpenMenu: (id: string | null) => void;
}) {
  const [view, setView] = useState<MarkView>("all");
  const [hiddenCats, setHiddenCats] = useState<Set<string>>(() => showAllCategories());
  const [search, setSearch] = useState("");

  const rows = useMemo(
    () => filterMarkedCandidates(candidates, { view, hiddenCats, search }),
    [candidates, view, hiddenCats, search],
  );
  const totalMarked = useMemo(() => candidates.filter(isMarked).length, [candidates]);

  return (
    <>
      {error && <p className="err marked-error">{error}</p>}
      <div className="filter-bar">
        <div className="segmented">
          {MARK_VIEWS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              className={view === opt.id ? "on" : ""}
              onClick={() => setView(opt.id)}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <CheckMenu
          id="marked-categories"
          label="Categories"
          summary={
            allCategoriesOn(hiddenCats, categories)
              ? undefined
              : String(onCategoryCount(hiddenCats, categories))
          }
          openId={openMenu}
          setOpenId={setOpenMenu}
        >
          <label className="menu-check">
            <input
              type="checkbox"
              checked={allCategoriesOn(hiddenCats, categories)}
              onChange={(e) =>
                setHiddenCats(e.target.checked ? showAllCategories() : hideAllCategories(categories))
              }
            />
            All categories
          </label>
          <label className="menu-check">
            <input
              type="checkbox"
              checked={isCategoryOn(hiddenCats, UNCATEGORISED)}
              onChange={(e) =>
                setHiddenCats((prev) =>
                  toggleCategoryVisibility(prev, UNCATEGORISED, e.target.checked),
                )
              }
            />
            Uncategorised
          </label>
          {categories.map((cat) => (
            <label key={cat.id} className="menu-check">
              <input
                type="checkbox"
                checked={isCategoryOn(hiddenCats, String(cat.id))}
                onChange={(e) =>
                  setHiddenCats((prev) =>
                    toggleCategoryVisibility(prev, String(cat.id), e.target.checked),
                  )
                }
              />
              {cat.name}
            </label>
          ))}
          <NewCategoryForm onSave={onAddCategory} />
        </CheckMenu>
        <input
          type="search"
          placeholder="Search topic, idea, comment, title…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button
          type="button"
          className="btn-quiet"
          onClick={() => {
            setView("all");
            setHiddenCats(showAllCategories());
            setSearch("");
          }}
        >
          Clear
        </button>
        <span className="filter-count">{rows.length} shown</span>
      </div>

      <main id="marked-list">
        {rows.length === 0 ? (
          <div className="empty-queue">
            {totalMarked === 0
              ? "Nothing marked yet. Mark an item important or shortlist it in Review and it shows up here."
              : "No marked items match these filters."}
          </div>
        ) : (
          rows.map((c) => (
            <MarkedRow
              key={c.id}
              c={c}
              categories={categories}
              onPatch={onPatch}
              onAddCategory={onAddCategory}
              onOpenEmail={onOpenEmail}
            />
          ))
        )}
      </main>
    </>
  );
}

const HIT_VIEWS: { id: HitView; label: string }[] = [
  { id: "all", label: "All findings" },
  { id: "direct", label: "Direct answers" },
  { id: "related", label: "Related" },
];

const EXAMPLE_QUESTION =
  "List the studies and papers mentioned in the emails that conclude the harness affects how well models perform on benchmark tasks.";

/**
 * Agentic search over the stored emails: the backend reads the range in batches
 * and streams findings back, so results appear while the search is still going.
 */
function SearchView({
  onOpenEmail,
  setError,
  error,
  categories,
  onAddCategory,
  onKept,
}: {
  onOpenEmail: (id: number, excerpt: string) => void;
  setError: (s: string) => void;
  error: string;
  categories: Category[];
  onAddCategory: (name: string) => Promise<Category>;
  onKept: (c: Candidate) => void;
}) {
  const [question, setQuestion] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [history, setHistory] = useState<IdeaSearch[]>([]);
  const [active, setActive] = useState<IdeaSearchDetail | null>(null);
  const [preview, setPreview] = useState<SearchPreview | null>(null);
  const [starting, setStarting] = useState(false);
  const [hitView, setHitView] = useState<HitView>("all");
  const [hitSearch, setHitSearch] = useState("");
  const [keepHit, setKeepHit] = useState<SearchHit | null>(null);
  const [now, setNow] = useState(Date.now());

  const running = isSearchRunning(active);

  const openSearch = useCallback(
    async (id: number) => {
      try {
        setActive(await api.search(id));
        setHitView("all");
        setHitSearch("");
      } catch (e) {
        setError((e as Error).message);
      }
    },
    [setError],
  );

  // Reattach to a search still running from an earlier visit or page reload.
  useEffect(() => {
    api
      .searches()
      .then((rows) => {
        setHistory(rows);
        const live = rows.find(isSearchRunning);
        if (live) openSearch(live.id);
      })
      .catch((e: Error) => setError(e.message));
  }, [openSearch, setError]);

  useEffect(() => {
    if (!from && !to) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    const t = setTimeout(() => {
      api
        .searchPreview({ date_from: from || undefined, date_to: to || undefined })
        .then((p) => {
          if (!cancelled) setPreview(p);
        })
        .catch(() => undefined);
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [from, to]);

  useEffect(() => {
    if (!running || !active) return;
    const id = active.id;
    const tick = setInterval(() => setNow(Date.now()), 1000);
    const poll = setInterval(async () => {
      try {
        const next = await api.search(id);
        setActive(next);
        if (!isSearchRunning(next)) {
          api.searches().then(setHistory).catch(() => undefined);
        }
      } catch {
        /* ignore poll errors */
      }
    }, 2000);
    return () => {
      clearInterval(tick);
      clearInterval(poll);
    };
  }, [running, active?.id]);

  async function run() {
    const q = question.trim();
    if (!q || starting) return;
    setStarting(true);
    setError("");
    try {
      const created = await api.createSearch({
        question: q,
        date_from: from || undefined,
        date_to: to || undefined,
      });
      setHistory((prev) => [created, ...prev]);
      setActive({ ...created, hits: [] });
      setHitView("all");
      setHitSearch("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(false);
    }
  }

  async function remove(id: number) {
    try {
      await api.deleteSearch(id);
      setHistory((prev) => prev.filter((s) => s.id !== id));
      if (active?.id === id) setActive(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const pastSearches = useMemo(() => sortSearchesNewestFirst(history), [history]);
  const hits = active?.hits ?? [];
  const counts = useMemo(() => countByRelevance(hits), [hits]);
  const shown = useMemo(
    () => filterHits(hits, { view: hitView, search: hitSearch }),
    [hits, hitView, hitSearch],
  );
  const progress = active ? searchProgress(active) : null;

  return (
    <>
      <section className="search-panel">
        <h2>Ask a question across your emails</h2>
        <p className="search-intro">
          Every newsletter in the range is read in batches by GPT-5.4, which quotes the
          passages that bear on your question and says why each one is relevant. Missing
          issues are pulled from Gmail first; anything already stored is left as-is.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            run();
          }}
        >
          <textarea
            rows={3}
            value={question}
            placeholder={EXAMPLE_QUESTION}
            aria-label="Your question"
            disabled={starting || running}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) run();
            }}
          />
          <div className="search-controls">
            <label className="date-mini">
              From
              <input
                type="date"
                value={from}
                disabled={starting || running}
                onChange={(e) => setFrom(e.target.value)}
              />
            </label>
            <label className="date-mini">
              To
              <input
                type="date"
                value={to}
                disabled={starting || running}
                onChange={(e) => setTo(e.target.value)}
              />
            </label>
            <button
              type="submit"
              className="btn-primary"
              disabled={starting || running || !question.trim()}
            >
              {running ? "Searching…" : "Search emails"}
            </button>
            {!question.trim() && (
              <button
                type="button"
                className="btn-quiet"
                onClick={() => setQuestion(EXAMPLE_QUESTION)}
              >
                Use the example
              </button>
            )}
            <span className="search-scope">
              {preview ? searchScopeLabel(preview) : ""}
            </span>
          </div>
        </form>
        {error && <p className="err">{error}</p>}
      </section>

      {pastSearches.length > 0 && (
        <details className="search-history">
          <summary>View my past searches</summary>
          <p className="search-history-hint">
            Click a row to open the saved findings. It does not run the search again.
          </p>
          <table className="search-history-table">
            <thead>
              <tr>
                <th>Search date</th>
                <th>Question</th>
                <th>Date range</th>
                <th>
                  <span className="sr-only">Delete</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {pastSearches.map((s) => (
                <tr
                  key={s.id}
                  className={active?.id === s.id ? "on" : ""}
                  onClick={() => openSearch(s.id)}
                >
                  <td className="search-history-when">
                    {searchWhenLabel(s.created_at)}
                    {isSearchRunning(s) ? " · running" : ""}
                  </td>
                  <td className="search-history-question" title={s.question}>
                    {s.question}
                  </td>
                  <td className="search-history-range">{searchRangeLabel(s)}</td>
                  <td className="search-history-delete">
                    <button
                      type="button"
                      className="chip-x"
                      aria-label="Delete this search"
                      onClick={(e) => {
                        e.stopPropagation();
                        remove(s.id);
                      }}
                    >
                      ×
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}

      {active && (
        <section className="search-result-head">
          <h2>{active.question}</h2>
          <p className="meta">
            {searchRangeLabel(active)} · {searchStatusLine(active)}
            {running ? ` · ${elapsed(active.created_at, now)} elapsed` : ""}
          </p>
          {running && progress && (
            <div className="progress-track" aria-hidden="true">
              <div
                className={`progress-fill ${progress.determinate ? "" : "indeterminate"}`}
                style={progress.determinate ? { width: `${progress.pct}%` } : undefined}
              />
            </div>
          )}
          {hits.length > 0 && (
            <div className="filter-bar">
              <div className="segmented">
                {HIT_VIEWS.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    className={hitView === opt.id ? "on" : ""}
                    onClick={() => setHitView(opt.id)}
                  >
                    {opt.label}
                    {opt.id === "direct" && counts.direct ? ` · ${counts.direct}` : ""}
                    {opt.id === "related" && counts.related ? ` · ${counts.related}` : ""}
                  </button>
                ))}
              </div>
              <input
                type="search"
                placeholder="Search within findings…"
                value={hitSearch}
                onChange={(e) => setHitSearch(e.target.value)}
              />
              <span className="filter-count">{shown.length} shown</span>
            </div>
          )}
        </section>
      )}

      <main id="search-results">
        {!active ? (
          <div className="empty-queue">
            Ask a question above. The search reads whole newsletters, so it finds passages that a
            keyword search would miss.
          </div>
        ) : shown.length === 0 ? (
          <div className="empty-queue">
            {running
              ? "Reading the emails. Findings appear here as each batch comes back."
              : hits.length === 0
                ? "Nothing in these emails answers that question. Try widening the date range or asking it a different way."
                : "No findings match this filter."}
          </div>
        ) : (
          shown.map((h) => (
            <HitCard
              key={h.id}
              h={h}
              onOpenEmail={onOpenEmail}
              onKeep={() => setKeepHit(h)}
            />
          ))
        )}
      </main>

      {keepHit && active && (
        <KeepHitPrompt
          hit={keepHit}
          categories={categories}
          onAddCategory={onAddCategory}
          onClose={() => setKeepHit(null)}
          onSave={async (body) => {
            const out = await api.keepHit(active.id, keepHit.id, body);
            setActive((prev) =>
              prev
                ? { ...prev, hits: prev.hits.map((h) => (h.id === out.hit.id ? out.hit : h)) }
                : prev,
            );
            onKept(out.candidate);
            setKeepHit(null);
          }}
        />
      )}
    </>
  );
}

function HitCard({
  h,
  onOpenEmail,
  onKeep,
}: {
  h: SearchHit;
  onOpenEmail: (id: number, excerpt: string) => void;
  onKeep: () => void;
}) {
  return (
    <article className={`hit-card ${h.relevance === "direct" ? "is-direct" : ""}`}>
      <div className="card-top">
        <div>
          <span className={`badge ${h.relevance === "direct" ? "hit-direct" : "hit-related"}`}>
            {relevanceLabel(h.relevance)}
          </span>
          {h.candidate_id ? (
            <span className="badge important-flag">Added to marked items</span>
          ) : null}
        </div>
        {h.candidate_id ? null : (
          <button type="button" className="btn-primary" onClick={onKeep}>
            Add to marked items
          </button>
        )}
      </div>
      <h2>{h.title || "Finding"}</h2>
      <p className="meta">
        {h.email_date || h.date_iso} ·{" "}
        <button type="button" className="linkish" onClick={() => onOpenEmail(h.email_id, h.excerpt)}>
          {h.email_title || `Email ${h.email_id}`}
        </button>
      </p>
      <blockquote className="excerpt">
        <MarkdownInline text={h.excerpt} />
      </blockquote>
      {h.why_relevant && (
        <p className="hit-why">
          <span className="hit-why-label">Why this matters</span>
          {h.why_relevant}
        </p>
      )}
    </article>
  );
}

const KEEP_TAGS: { value: string; label: string; slug: string }[] = [
  { value: "HIGH PRIORITY RESEARCH AREA", label: "High priority", slug: "high-priority" },
  { value: "STRONG CANDIDATE", label: "Strong", slug: "strong" },
  { value: "POSSIBLE CANDIDATE", label: "Possible", slug: "possible" },
];

function KeepHitPrompt({
  hit,
  categories,
  onAddCategory,
  onSave,
  onClose,
}: {
  hit: SearchHit;
  categories: Category[];
  onAddCategory: (name: string) => Promise<Category>;
  onSave: (body: {
    tag: string;
    category_id: number;
    notes: string;
    important: boolean;
    shortlisted: boolean;
  }) => Promise<void>;
  onClose: () => void;
}) {
  const [tag, setTag] = useState("");
  const [categoryId, setCategoryId] = useState<number | "">("");
  const [adding, setAdding] = useState(false);
  const [notes, setNotes] = useState("");
  const [important, setImportant] = useState(true);
  const [shortlisted, setShortlisted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState("");

  const canSave = Boolean(tag && categoryId && (important || shortlisted) && !busy);

  async function save() {
    if (!canSave || typeof categoryId !== "number") return;
    setBusy(true);
    setLocalError("");
    try {
      await onSave({
        tag,
        category_id: categoryId,
        notes: notes.trim(),
        important,
        shortlisted,
      });
    } catch (e) {
      setLocalError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <>
      <div className="email-backdrop" onClick={onClose} />
      <form
        className="comment-modal keep-modal"
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
      >
        <h2>Add to marked items</h2>
        <p className="meta">{hit.title || "This finding"}</p>

        <p className="prompt-category-label">How would you rank it?</p>
        <div className="segmented keep-tags">
          {KEEP_TAGS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className={tag === opt.value ? "on" : ""}
              disabled={busy}
              onClick={() => setTag(opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <div className={`prompt-category ${categoryId ? "" : "missing"}`}>
          <span className="prompt-category-label">
            {categoryId ? "Category" : "Assign a category"}
          </span>
          {adding ? (
            <NewCategoryForm
              onSave={async (name) => {
                const cat = await onAddCategory(name);
                setCategoryId(cat.id);
                setAdding(false);
              }}
              onCancel={() => setAdding(false)}
            />
          ) : (
            <select
              value={categoryId}
              aria-label="Category"
              disabled={busy}
              onChange={(e) => {
                if (e.target.value === "__new__") {
                  setAdding(true);
                  return;
                }
                setCategoryId(e.target.value ? Number(e.target.value) : "");
              }}
            >
              <option value="">Categorise…</option>
              {categories.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.name}
                </option>
              ))}
              <option value="__new__">+ Add new category…</option>
            </select>
          )}
        </div>

        <div className="keep-marks">
          <button
            type="button"
            className={`btn-important ${important ? "is-on" : ""}`}
            disabled={busy}
            onClick={() => setImportant((v) => !v)}
          >
            {important ? "Important" : "Mark Important"}
          </button>
          <button
            type="button"
            className={`btn-shortlist ${shortlisted ? "is-on" : ""}`}
            disabled={busy}
            onClick={() => setShortlisted((v) => !v)}
          >
            {shortlisted ? "Shortlisted for Probe" : "Shortlist for Probe"}
          </button>
        </div>

        <textarea
          rows={3}
          value={notes}
          disabled={busy}
          placeholder="Why is this worth a probe? (optional)"
          aria-label="Your comment"
          onChange={(e) => setNotes(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save();
          }}
        />
        {localError && <p className="err">{localError}</p>}
        <div className="comment-form-actions">
          <button type="submit" className="btn-primary" disabled={!canSave}>
            Add to marked items
          </button>
          <button type="button" className="btn-quiet" onClick={onClose} disabled={busy}>
            Cancel
          </button>
        </div>
      </form>
    </>
  );
}

function PublishControl({
  status,
  onPublish,
}: {
  status: PublishStatus;
  onPublish: () => void;
}) {
  const busy = status.status === "running";
  return (
    <div className="publish-control">
      <button
        type="button"
        className="publish-btn"
        disabled={busy}
        onClick={onPublish}
        title={status.error || undefined}
      >
        {busy ? "Publishing…" : "Publish snapshot"}
      </button>
      {status.status === "done" && status.url && (
        <a className="publish-link" href={status.url} target="_blank" rel="noreferrer">
          View public page
        </a>
      )}
      {status.status === "error" && (
        <span className="publish-err" title={status.error}>Publish failed</span>
      )}
    </div>
  );
}

function GmailControl({
  settings,
  onChange,
  setError,
}: {
  settings: SettingsStatus | null;
  onChange: (s: SettingsStatus) => void;
  setError: (s: string) => void;
}) {
  if (!settings) {
    return <span className="gmail-chip">Checking Gmail…</span>;
  }
  if (settings.connected) {
    return (
      <span className="gmail-chip ok">
        Gmail · {settings.email || "connected"}
        <button
          type="button"
          className="btn-quiet chip-action"
          onClick={async () => {
            try {
              onChange(await api.disconnect());
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        >
          Disconnect
        </button>
      </span>
    );
  }
  if (!settings.has_client) {
    return <span className="gmail-chip warn">Add Gmail OAuth client to .env</span>;
  }
  return (
    <button
      type="button"
      className="btn-primary"
      onClick={async () => {
        try {
          const { auth_url } = await api.connectUrl();
          window.location.href = auth_url;
        } catch (e) {
          setError((e as Error).message);
        }
      }}
    >
      Connect Gmail
    </button>
  );
}
