import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  getStoredToken,
  setStoredToken,
  type AuthStatus,
  type Candidate,
  type Category,
  type EmailDetail,
  type IdeaSearch,
  type IdeaSearchDetail,
  type Job,
  type PublishStatus,
  type LlmLogDetail,
  type LlmLogSummary,
  type ResearchContext,
  type ResearchItem,
  type ResearchNotUseful,
  type ResearchPriority,
  type Role,
  type SearchHit,
  type SearchPreview,
  type SettingsStatus,
  type Stats,
} from "./api";
import { MarkdownBody, MarkdownInline } from "./markdown";
import {
  UNCATEGORISED,
  allCategoriesOn,
  categoryKey,
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

type TabId = "review" | "marked" | "search" | "admin";

const TABS: { id: TabId; label: string; sub: string; adminOnly?: boolean }[] = [
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
    label: "Semantic search",
    sub: "Ask a question across full newsletters",
  },
  {
    id: "admin",
    label: "Admin",
    sub: "Research context and categories",
    adminOnly: true,
  },
];

const MARK_OPTIONS: { id: MarkFilter; label: string }[] = [
  { id: "important", label: "Marked important by user" },
  { id: "shortlist", label: "Shortlisted by user" },
];

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

function formatOverviewDate(iso: string) {
  if (!iso) return "";
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return iso;
  return new Date(ms).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function countByCategory(candidates: Candidate[]): Record<string, number> {
  const counts: Record<string, number> = { [UNCATEGORISED]: 0 };
  for (const c of candidates) {
    if (c.deleted) continue;
    const key = categoryKey(c.category_id);
    counts[key] = (counts[key] || 0) + 1;
  }
  return counts;
}

function truncate(text: string, n = 80) {
  const t = text.trim();
  return t.length > n ? t.slice(0, n - 1) + "…" : t;
}

/** The daily pull hour, written the way a clock reads it. */
function syncHourLabel(hour: number) {
  const h = Number.isFinite(hour) ? ((Math.trunc(hour) % 24) + 24) % 24 : 0;
  const suffix = h < 12 ? "am" : "pm";
  const twelve = h % 12 === 0 ? 12 : h % 12;
  return `${twelve}${suffix}`;
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

/** Category dropdown that can also create a category on the spot (admin). */
function CategoryPicker({
  c,
  categories,
  onPatch,
  onAddCategory,
  canEdit = true,
  canAdmin = false,
}: {
  c: Candidate;
  categories: Category[];
  onPatch: (id: number, body: Record<string, unknown>) => Promise<boolean>;
  onAddCategory: (name: string) => Promise<Category>;
  canEdit?: boolean;
  canAdmin?: boolean;
}) {
  const [adding, setAdding] = useState(false);
  const options = categories.filter(
    (cat) => !cat.deprecated || cat.id === c.category_id,
  );

  if (!canEdit) {
    return (
      <span className="category-readonly" title={c.category_name || "Uncategorised"}>
        {c.category_name || "Uncategorised"}
      </span>
    );
  }

  if (adding && canAdmin) {
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
      {options.map((cat) => (
        <option key={cat.id} value={cat.id}>
          {cat.name}
          {cat.deprecated ? " (deprecated)" : ""}
        </option>
      ))}
      {canAdmin && <option value="__new__">+ Add new category…</option>}
    </select>
  );
}

/** The saved comment, with a way into the editor. */
function CommentDisplay({
  c,
  onEdit,
  canEdit = true,
}: {
  c: Candidate;
  onEdit: () => void;
  canEdit?: boolean;
}) {
  if (c.notes) {
    return (
      <div className="comment">
        <p className="field-label">User comment:</p>
        <p className="comment-text">{c.notes}</p>
        {canEdit && (
          <button type="button" className="linkish" onClick={onEdit}>
            Edit comment
          </button>
        )}
      </div>
    );
  }
  if (!canEdit || !isMarked(c)) return null;
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
  canAdmin = false,
}: {
  c: Candidate;
  categories: Category[];
  onPatch: (id: number, body: Record<string, unknown>) => Promise<boolean>;
  onAddCategory: (name: string) => Promise<Category>;
  onSave: (text: string) => Promise<unknown>;
  onClose: () => void;
  canAdmin?: boolean;
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
            canAdmin={canAdmin}
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
  const [stats, setStats] = useState<Stats | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [settings, setSettings] = useState<SettingsStatus | null>(null);
  const [view, setView] = useState<TabId>("review");
  const [role, setRole] = useState<Role>("viewer");
  const [authMeta, setAuthMeta] = useState<AuthStatus | null>(null);
  const [signInOpen, setSignInOpen] = useState(false);
  const [unprocessedOnly, setUnprocessedOnly] = useState(true);
  const [tagFilters, setTagFilters] = useState<Set<TagFilter>>(new Set());
  const [markFilters, setMarkFilters] = useState<Set<MarkFilter>>(new Set());
  const [search, setSearch] = useState("");
  const [searchAllDb, setSearchAllDb] = useState(false);
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
  const [now, setNow] = useState(Date.now());
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
    try {
      setSettings(await api.settings());
    } catch (e) {
      setError((e as Error).message);
    }
    try {
      const auth = await api.authStatus();
      setAuthMeta(auth);
      setRole(auth.role);
    } catch {
      /* ignore */
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

  useEffect(() => {
    // Restore session token role on first paint.
    if (!getStoredToken()) return;
    api
      .authStatus()
      .then((auth) => {
        setAuthMeta(auth);
        setRole(auth.role);
      })
      .catch(() => undefined);
  }, []);

  const canEdit = role === "analyst" || role === "admin";
  const canAdmin = role === "admin";

  async function handleUnlock(token: string) {
    const auth = await api.unlock(token);
    setStoredToken(token.trim());
    setAuthMeta(auth);
    setRole(auth.role);
    setSignInOpen(false);
    setError("");
  }

  function handleSignOut() {
    setStoredToken("");
    setRole("viewer");
    if (view === "admin") setView("review");
    api
      .authStatus()
      .then((auth) => {
        setAuthMeta(auth);
        setRole(auth.role);
      })
      .catch(() => undefined);
  }

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

  const jobBusy = !!job && job.status !== "done" && job.status !== "failed";

  async function startSync() {
    setError("");
    setDismissedJobId(null);
    lastProgressLoad.current = "";
    setJob(await api.sync({ extract: true }));
  }

  async function requestSync() {
    setError("");
    setDismissedJobId(null);
    if (settings && !settings.inbox_configured) {
      setError("Set up the dedicated inbox in .env first.");
      return;
    }
    try {
      await startSync();
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

  const keywordActive = !!search.trim();
  const searchingAllDb = keywordActive && searchAllDb;

  const visible = useMemo(
    () =>
      filterCandidates(candidates, {
        tagFilters,
        markFilters,
        search,
        searchAllDb,
        dateFrom,
        dateTo,
        hiddenCats,
      }),
    [candidates, tagFilters, markFilters, search, searchAllDb, dateFrom, dateTo, hiddenCats],
  );

  // While searching the whole DB, show every match in one processable list.
  const hideProcessedInMain =
    !searchingAllDb && unprocessedOnly && markFilters.size === 0;
  const mainCards = hideProcessedInMain ? visible.filter((c) => !c.processed) : visible;
  const processedCards = hideProcessedInMain ? visible.filter((c) => c.processed) : [];

  function resetReviewFilters() {
    setUnprocessedOnly(true);
    setTagFilters(new Set());
    setMarkFilters(new Set());
    setSearch("");
    setSearchAllDb(false);
    setDateFrom("");
    setDateTo("");
    setHiddenCats(showAllCategories());
  }

  const showJob = job && job.id !== dismissedJobId;
  const markedCount = useMemo(() => candidates.filter(isMarked).length, [candidates]);
  const categoryCounts = useMemo(() => countByCategory(candidates), [candidates]);
  const summaryCounts = useMemo(() => {
    let important = 0;
    let shortlisted = 0;
    let processed = 0;
    let unprocessed = 0;
    for (const c of candidates) {
      if (c.deleted) continue;
      if (c.important) important += 1;
      if (c.shortlisted) shortlisted += 1;
      if (c.important || c.shortlisted) processed += 1;
      else unprocessed += 1;
    }
    return { important, shortlisted, processed, unprocessed };
  }, [candidates]);
  const commentCandidate = commentFor
    ? candidates.find((c) => c.id === commentFor) ?? null
    : null;

  return (
    <div className="app-shell">
      <div className="app-chrome">
        <header className="app-header">
          <div>
            <h1>AI News Newsletter Explorer</h1>
            {role === "viewer" && (
              <p className="viewer-hint">Viewing only — sign in to mark items or sync.</p>
            )}
          </div>
          <div className="header-right">
            <AuthChip
              role={role}
              onSignIn={() => setSignInOpen(true)}
              onSignOut={handleSignOut}
            />
            {canEdit && <PublishControl status={publishStatus} onPublish={startPublish} />}
            <InboxStatus settings={settings} />
          </div>
        </header>

        <nav className="tabs" role="tablist" aria-label="Sections">
          {TABS.filter((tab) => !tab.adminOnly || canAdmin).map((tab) => {
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

        {view === "review" && (
          <>
            <div className="overview-strip">
              <span className="overview-range">
                {stats?.date_from && stats?.date_to
                  ? `Available newsletters: ${formatOverviewDate(stats.date_from)} to ${formatOverviewDate(stats.date_to)}`
                  : stats?.emails
                    ? `Available newsletters: ${stats.emails} in the database`
                    : "Available newsletters: none yet"}
              </span>
              <span className="overview-stat">
                Shortlisted for probes: <strong>{summaryCounts.shortlisted}</strong>
              </span>
              <span className="overview-stat">
                Marked important: <strong>{summaryCounts.important}</strong>
              </span>
              <span className="overview-stat">
                Processed: <strong>{summaryCounts.processed}</strong>
              </span>
              <span className="overview-stat">
                Unprocessed: <strong>{summaryCounts.unprocessed}</strong>
              </span>
            </div>

            <JobPanel
              settings={settings}
              job={showJob ? job : null}
              busy={jobBusy}
              error={error}
              now={now}
              canEdit={canEdit}
              onSignIn={() => setSignInOpen(true)}
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
                    {cat.name} ({categoryCounts[String(cat.id)] || 0})
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
                onClick={resetReviewFilters}
              >
                Clear
              </button>
              <span className="filter-count">{mainCards.length} shown</span>
            </div>
            <div className="keyword-filter-row">
              <div className="keyword-filter-heading">
                <h3 className="keyword-filter-title">Keyword Search</h3>
                <span className="info-tip">
                  <button
                    type="button"
                    className="info-tip-btn"
                    aria-label="About keyword search"
                  >
                    i
                  </button>
                  <span className="info-tip-bubble" role="tooltip">
                    By default, keyword search only filters the items currently displayed
                    by the filters above (case-insensitive match on topic, idea, snippet,
                    and title). Tick “Search all candidates in the database” to run the
                    same keyword search over every extracted candidate in the database.
                    For semantic search over full newsletters, use the Semantic search tab.
                  </span>
                </span>
              </div>
              <div className="keyword-filter-controls">
                <label className="keyword-scope">
                  <input
                    type="checkbox"
                    checked={searchAllDb}
                    onChange={(e) => setSearchAllDb(e.target.checked)}
                  />
                  Search all candidates in the database
                </label>
                <input
                  type="search"
                  placeholder="Filter by topic, idea, snippet, or title…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                {keywordActive && (
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={resetReviewFilters}
                  >
                    Done with search
                  </button>
                )}
              </div>
              {searchingAllDb && (
                <p className="keyword-filter-banner">
                  Showing {visible.length} match{visible.length === 1 ? "" : "es"} across all
                  candidates in the database. Process them here, then click Done with search to
                  return to the default view.
                </p>
              )}
            </div>
          </>
        )}
      </div>

      <div className="app-scroll">
      {view === "admin" && canAdmin ? (
        <AdminView
          categories={categories}
          setCategories={setCategories}
          setError={setError}
          error={error}
        />
      ) : view === "search" ? (
        <SearchView
          onOpenEmail={openEmail}
          setError={setError}
          error={error}
          categories={categories}
          onAddCategory={addCategory}
          canEdit={canEdit}
          canAdmin={canAdmin}
          onSignIn={() => setSignInOpen(true)}
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
          categoryCounts={categoryCounts}
          error={error}
          onPatch={patch}
          onAddCategory={addCategory}
          onOpenEmail={openEmail}
          openMenu={openMenu}
          setOpenMenu={setOpenMenu}
          canEdit={canEdit}
          canAdmin={canAdmin}
        />
      ) : (
        <>
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
                    canEdit={canEdit}
                    canAdmin={canAdmin}
                  />
                ))}
              </div>
            </details>
          )}

          <p className="section-label">
            {searchingAllDb
              ? "Keyword search results"
              : unprocessedOnly && markFilters.size === 0
                ? "Unprocessed queue"
                : "Queue"}
          </p>
          <main id="candidate-list">
            {mainCards.length === 0 ? (
              <div className="empty-queue">
                {keywordActive
                  ? searchingAllDb
                    ? "No candidates in the database match that keyword."
                    : "No displayed results match that keyword."
                  : filtersAreDefault(
                      {
                        tagFilters,
                        markFilters,
                        search,
                        searchAllDb,
                        dateFrom,
                        dateTo,
                        hiddenCats,
                      },
                      categories,
                    )
                  ? "No unprocessed candidates. New newsletters arrive in the dedicated inbox and are pulled in automatically each day — or click Sync inbox now to pull them straight away."
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
                  canEdit={canEdit}
                  canAdmin={canAdmin}
                />
            ))
          )}
          </main>
        </>
      )}

      {commentCandidate && canEdit && (
        <CommentPrompt
          c={commentCandidate}
          categories={categories}
          onPatch={patch}
          onAddCategory={addCategory}
          canAdmin={canAdmin}
          onSave={async (text) => {
            // Keep the editor open on failure so the comment is not lost.
            if (text === commentCandidate.notes) setCommentFor(null);
            else if (await patch(commentCandidate.id, { notes: text })) setCommentFor(null);
          }}
          onClose={() => setCommentFor(null)}
        />
      )}

      {signInOpen && (
        <SignInModal
          authMeta={authMeta}
          onUnlock={handleUnlock}
          onClose={() => setSignInOpen(false)}
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
    </div>
  );
}

function JobPanel({
  settings,
  job,
  busy,
  error,
  now,
  canEdit,
  onSignIn,
  onSync,
  onDismiss,
}: {
  settings: SettingsStatus | null;
  job: Job | null;
  busy: boolean;
  error: string;
  now: number;
  canEdit: boolean;
  onSignIn: () => void;
  onSync: () => void;
  onDismiss: () => void;
}) {
  return (
    <section className="job-panel">
      <div className="job-row">
        {canEdit ? (
          <button type="button" className="btn-primary" disabled={busy} onClick={onSync}>
            Sync inbox now
          </button>
        ) : (
          <button type="button" className="btn-primary" onClick={onSignIn}>
            Sign in to sync
          </button>
        )}
      </div>
      {!job && (
        <p className="job-idle">
          {!settings
            ? "Checking the dedicated inbox…"
            : !settings.inbox_configured
              ? "Set IMAP_USER, IMAP_PASSWORD, and IMAP_ALLOWED_FROM in .env and restart, so newsletters forwarded to the dedicated inbox can be pulled in."
              : canEdit
                ? `Forward newsletters to ${settings.inbox_email || "the dedicated inbox"} and they are pulled in ${
                    settings.inbox_enabled
                      ? `automatically every day at ${syncHourLabel(settings.sync_hour)}`
                      : "on request (the daily pull is switched off)"
                  }. Sync inbox now pulls anything new straight away, then GPT reads each new newsletter and extracts probe ideas (about 2–3 minutes per email).`
                : `Newsletters are pulled into ${settings.inbox_email || "the dedicated inbox"} automatically. You are viewing results — sign in as analyst to sync or mark items.`}
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
  const subject = str(p, "subject");
  const running = job.status === "queued" || job.status === "running";
  const isSync = job.kind === "sync";
  const downloading =
    phase === "connecting" ||
    phase === "listing" ||
    phase === "fetching" ||
    phase === "fetched";
  const extracting = phase === "extracting";

  let title = "Working…";
  let detail = "";
  let hint = "";
  let pct = 0;
  let determinate = false;

  if (job.status === "failed") {
    title = job.kind === "extract" ? "Extraction failed" : "Sync failed";
    detail = job.error || "Something went wrong.";
  } else if (phase === "connecting") {
    title = isSync ? "Step 1 of 2: Connecting to the inbox" : "Connecting to the inbox";
    detail = "Signing in to the dedicated mailbox.";
    hint = "The pull is usually quick. The slow part is next: GPT reads each new newsletter and extracts probe ideas.";
  } else if (phase === "listing") {
    title = isSync ? "Step 1 of 2: Finding emails in inbox" : "Finding emails in inbox";
    detail = "Listing messages from the allowed sender addresses.";
    hint = "The pull is usually quick. The slow part is next: GPT reads each new newsletter and extracts probe ideas.";
  } else if (phase === "fetching") {
    title = listed
      ? `Step 1 of 2: Downloading ${current} of ${listed} from inbox`
      : "Step 1 of 2: Downloading from inbox";
    detail = `${newEmails} new, ${skipped} already stored.`;
    hint = "After the pull, GPT extracts new or pending emails only. Already extracted newsletters are skipped.";
    determinate = listed > 0;
    pct = listed ? Math.min(100, (current / listed) * 100) : 0;
  } else if (phase === "fetched") {
    title = "Step 1 of 2: Inbox pull complete";
    detail = `${listed} message${listed === 1 ? "" : "s"} from the allowed senders. ${newEmails} new, ${skipped} already stored.`;
    hint =
      newEmails > 0
        ? `Starting idea extraction for ${newEmails} new email${newEmails === 1 ? "" : "s"}.`
        : "No new emails to process.";
    determinate = true;
    pct = 100;
  } else if (phase === "extracting") {
    const n = current || 0;
    const of = total || newEmails || 0;
    title = isSync
      ? of
        ? `Step 2 of 2: Extracting probe ideas — ${n} of ${of}`
        : "Step 2 of 2: Extracting probe ideas"
      : of
        ? `Extracting probe ideas — ${n} of ${of}`
        : "Extracting probe ideas";
    detail = subject
      ? `GPT-5.4 is reading “${truncate(subject, 90)}” and pulling out probe ideas.`
      : "GPT-5.4 is reading each newsletter and pulling out probe ideas.";
    const eta = remainingEstimate(n, of);
    hint = [
      "This is the slow part — about 2–3 minutes per email with high reasoning.",
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
    if (newEmails === 0 && extracted === 0 && skippedExtracted > 0) {
      title = "Already extracted";
      detail = `Nothing new in the inbox. ${skippedExtracted} newsletter${skippedExtracted === 1 ? " was" : "s were"} already processed — GPT was not re-run.`;
    } else {
      const parts = [];
      if (listed) parts.push(`${listed} message${listed === 1 ? "" : "s"} in the inbox`);
      if (newEmails || skipped) parts.push(`${newEmails} new, ${skipped} already stored`);
      if (extracted) {
        parts.push(`Extracted ideas from ${extracted} email${extracted === 1 ? "" : "s"}`);
      } else {
        parts.push("No new ideas extracted");
      }
      if (skippedExtracted) {
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
              Pull from inbox
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
  canEdit = true,
  canAdmin = false,
}: {
  c: Candidate;
  categories: Category[];
  onPatch: (id: number, body: Record<string, unknown>) => Promise<boolean>;
  onAddCategory: (name: string) => Promise<Category>;
  onOpenEmail: (id: number, excerpt: string) => void;
  onComment: (id: number) => void;
  canEdit?: boolean;
  canAdmin?: boolean;
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
            canEdit={canEdit}
            canAdmin={canAdmin}
          />
          {canEdit ? (
            <>
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
            </>
          ) : null}
        </div>
      </div>
      <h2>{c.topic}</h2>
      <p className="meta">
        {c.email_date || c.date_iso} ·{" "}
        <button type="button" className="linkish" onClick={() => onOpenEmail(c.email_id, c.excerpt)}>
          {c.email_title}
        </button>
      </p>
      <div className="field-block">
        <p className="field-label">AI News snippet:</p>
        <blockquote className="excerpt">
          <MarkdownInline text={c.excerpt} />
        </blockquote>
      </div>
      <div className="field-block">
        <p className="field-label">Analyzer agent comment:</p>
        <p className="idea">{c.main_idea}</p>
      </div>
      <CommentDisplay c={c} onEdit={() => onComment(c.id)} canEdit={canEdit} />
    </article>
  );
}

function MarkedRow({
  c,
  categories,
  onPatch,
  onAddCategory,
  onOpenEmail,
  canEdit = true,
  canAdmin = false,
}: {
  c: Candidate;
  categories: Category[];
  onPatch: (id: number, body: Record<string, unknown>) => Promise<boolean>;
  onAddCategory: (name: string) => Promise<Category>;
  onOpenEmail: (id: number, excerpt: string) => void;
  canEdit?: boolean;
  canAdmin?: boolean;
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
      <div className="field-block">
        <p className="field-label">AI News snippet:</p>
        <blockquote className="excerpt">
          <MarkdownInline text={c.excerpt} />
        </blockquote>
      </div>
      <div className="field-block">
        <p className="field-label">Analyzer agent comment:</p>
        <p className="idea">{c.main_idea}</p>
      </div>
      {editing && canEdit ? (
        <CommentBox
          value={c.notes}
          onSave={async (text) => {
            if (text === c.notes) setEditing(false);
            else if (await onPatch(c.id, { notes: text })) setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <CommentDisplay c={c} onEdit={() => setEditing(true)} canEdit={canEdit} />
      )}
      {canEdit && (
        <div className="marked-actions">
          <CategoryPicker
            c={c}
            categories={categories}
            onPatch={onPatch}
            onAddCategory={onAddCategory}
            canAdmin={canAdmin}
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
      )}
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
  categoryCounts,
  error,
  onPatch,
  onAddCategory,
  onOpenEmail,
  openMenu,
  setOpenMenu,
  canEdit = true,
  canAdmin = false,
}: {
  candidates: Candidate[];
  categories: Category[];
  categoryCounts: Record<string, number>;
  error: string;
  onPatch: (id: number, body: Record<string, unknown>) => Promise<boolean>;
  onAddCategory: (name: string) => Promise<Category>;
  onOpenEmail: (id: number, excerpt: string) => void;
  openMenu: string | null;
  setOpenMenu: (id: string | null) => void;
  canEdit?: boolean;
  canAdmin?: boolean;
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
              {cat.name} ({categoryCounts[String(cat.id)] || 0})
            </label>
          ))}
          <NewCategoryForm onSave={onAddCategory} />
        </CheckMenu>
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
      <div className="keyword-filter-row">
        <label className="keyword-filter">
          <span className="keyword-filter-label">
            Keyword search over the candidate list on this tab (case-insensitive). Filters items
            already loaded from the database — not full newsletter text, and not semantic search.
          </span>
          <input
            type="search"
            placeholder="Filter by topic, idea, comment, or title…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
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
              canEdit={canEdit}
              canAdmin={canAdmin}
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
  canEdit = true,
  canAdmin = false,
  onSignIn,
}: {
  onOpenEmail: (id: number, excerpt: string) => void;
  setError: (s: string) => void;
  error: string;
  categories: Category[];
  onAddCategory: (name: string) => Promise<Category>;
  onKept: (c: Candidate) => void;
  canEdit?: boolean;
  canAdmin?: boolean;
  onSignIn?: () => void;
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
        <h2>Semantic search over full newsletters</h2>
        <p className="search-intro">
          Ask a question and GPT reads whole newsletters in batches, quoting the passages that
          bear on it. This is semantic search over full email text — not the keyword filter on
          the first tab. New forwards in the dedicated inbox are pulled in first when needed.
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
                    {canEdit ? (
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
                    ) : null}
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
              canEdit={canEdit}
              onKeep={() => setKeepHit(h)}
              onSignIn={onSignIn}
            />
          ))
        )}
      </main>

      {keepHit && active && canEdit && (
        <KeepHitPrompt
          hit={keepHit}
          categories={categories}
          onAddCategory={onAddCategory}
          canAdmin={canAdmin}
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
  canEdit = true,
  onSignIn,
}: {
  h: SearchHit;
  onOpenEmail: (id: number, excerpt: string) => void;
  onKeep: () => void;
  canEdit?: boolean;
  onSignIn?: () => void;
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
        {h.candidate_id ? null : canEdit ? (
          <button type="button" className="btn-primary" onClick={onKeep}>
            Add to marked items
          </button>
        ) : (
          <button type="button" className="btn-quiet" onClick={onSignIn}>
            Sign in to mark
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
  canAdmin = false,
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
  canAdmin?: boolean;
}) {
  const [tag, setTag] = useState("");
  const [categoryId, setCategoryId] = useState<number | "">("");
  const [adding, setAdding] = useState(false);
  const [notes, setNotes] = useState("");
  const [important, setImportant] = useState(true);
  const [shortlisted, setShortlisted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState("");
  const activeCats = categories.filter((cat) => !cat.deprecated);

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
          {adding && canAdmin ? (
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
              {activeCats.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.name}
                </option>
              ))}
              {canAdmin && <option value="__new__">+ Add new category…</option>}
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

function AuthChip({
  role,
  onSignIn,
  onSignOut,
}: {
  role: Role;
  onSignIn: () => void;
  onSignOut: () => void;
}) {
  if (role === "viewer") {
    return (
      <button type="button" className="auth-chip" onClick={onSignIn}>
        Sign in
      </button>
    );
  }
  return (
    <div className="auth-chip signed-in">
      <span className="auth-role">{role === "admin" ? "Admin" : "Analyst"}</span>
      <button type="button" className="linkish" onClick={onSignOut}>
        Sign out
      </button>
    </div>
  );
}

function SignInModal({
  authMeta,
  onUnlock,
  onClose,
}: {
  authMeta: AuthStatus | null;
  onUnlock: (token: string) => Promise<void>;
  onClose: () => void;
}) {
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState("");
  const [mode, setMode] = useState<"analyst" | "admin">("analyst");

  async function submit() {
    if (!token.trim() || busy) return;
    setBusy(true);
    setLocalError("");
    try {
      await onUnlock(token.trim());
    } catch (e) {
      setLocalError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="email-backdrop" onClick={onClose} />
      <div className="comment-modal sign-in-modal">
        <h2>Sign in</h2>
        <p className="meta">
          The app opens as a viewer. Paste an analyst or admin token from{" "}
          <code>.env</code> to unlock edits.
        </p>
        <div className="segmented sign-in-modes">
          <button
            type="button"
            className={mode === "analyst" ? "on" : ""}
            onClick={() => setMode("analyst")}
          >
            Analyst
          </button>
          <button
            type="button"
            className={mode === "admin" ? "on" : ""}
            onClick={() => setMode("admin")}
          >
            Admin
          </button>
        </div>
        <p className="sign-in-hint">
          {mode === "admin"
            ? "Admin can edit research priorities, past probes, and categories. Changes apply to new newsletters only — existing marks and comments are never wiped."
            : "Analyst can mark items, sync the inbox, extract, and publish. Viewers can still browse and run semantic search."}
        </p>
        {authMeta && mode === "analyst" && !authMeta.analyst_token_set && (
          <p className="err">ANALYST_TOKEN is not set in .env yet.</p>
        )}
        {authMeta && mode === "admin" && !authMeta.admin_token_set && (
          <p className="err">ADMIN_TOKEN is not set in .env yet.</p>
        )}
        <label className="sign-in-label">
          {mode === "admin" ? "Admin token" : "Analyst token"}
          <input
            type="password"
            autoFocus
            value={token}
            placeholder="Paste token"
            aria-label={mode === "admin" ? "Admin token" : "Analyst token"}
            disabled={busy}
            onChange={(e) => setToken(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
              if (e.key === "Escape") onClose();
            }}
          />
        </label>
        {localError && <p className="err">{localError}</p>}
        <div className="comment-form-actions">
          <button
            type="button"
            className="btn-primary"
            disabled={busy || !token.trim()}
            onClick={submit}
          >
            {busy ? "Checking…" : "Unlock"}
          </button>
          <button type="button" className="btn-quiet" onClick={onClose} disabled={busy}>
            Stay as viewer
          </button>
        </div>
      </div>
    </>
  );
}

function AdminPanel({
  id,
  title,
  count,
  openId,
  setOpenId,
  children,
}: {
  id: string;
  title: string;
  count?: number;
  openId: string | null;
  setOpenId: (id: string | null) => void;
  children: React.ReactNode;
}) {
  const open = openId === id;
  return (
    <section className={`admin-panel ${open ? "open" : ""}`}>
      <button
        type="button"
        className="admin-panel-head"
        aria-expanded={open}
        onClick={() => setOpenId(open ? null : id)}
      >
        <span className="admin-panel-title">{title}</span>
        {typeof count === "number" ? <span className="admin-panel-count">{count}</span> : null}
        <span className="admin-panel-chevron" aria-hidden>
          {open ? "▾" : "▸"}
        </span>
      </button>
      {open && <div className="admin-panel-body">{children}</div>}
    </section>
  );
}

function InfoTip({ text }: { text: string }) {
  return (
    <span className="info-tip">
      <button type="button" className="info-tip-btn" aria-label="More information">
        i
      </button>
      <span className="info-tip-bubble" role="tooltip">
        {text}
      </span>
    </span>
  );
}

function formatJsonish(text: string): string {
  const t = text.trim();
  if (!t) return "";
  try {
    return JSON.stringify(JSON.parse(t), null, 2);
  } catch {
    return text;
  }
}

function AdminView({
  categories,
  setCategories,
  setError,
  error,
}: {
  categories: Category[];
  setCategories: React.Dispatch<React.SetStateAction<Category[]>>;
  setError: (s: string) => void;
  error: string;
}) {
  const [ctx, setCtx] = useState<ResearchContext | null>(null);
  const [openPanel, setOpenPanel] = useState<string | null>("priorities");
  const [note, setNote] = useState("");
  const [newCat, setNewCat] = useState("");
  const [logs, setLogs] = useState<LlmLogSummary[]>([]);
  const [logDetail, setLogDetail] = useState<LlmLogDetail | null>(null);
  const [logKind, setLogKind] = useState("extract");
  const [busy, setBusy] = useState(false);

  // Manual add forms
  const [priName, setPriName] = useState("");
  const [priDesc, setPriDesc] = useState("");
  const [probeTitle, setProbeTitle] = useState("");
  const [probeDesc, setProbeDesc] = useState("");
  const [probeUrl, setProbeUrl] = useState("");
  const [artTitle, setArtTitle] = useState("");
  const [artDesc, setArtDesc] = useState("");
  const [artUrl, setArtUrl] = useState("");
  const [nuText, setNuText] = useState("");

  const reload = useCallback(async () => {
    const next = await api.researchContext();
    setCtx(next);
  }, []);

  useEffect(() => {
    reload().catch((e: Error) => setError(e.message));
  }, [reload, setError]);

  useEffect(() => {
    if (openPanel !== "logs") return;
    api
      .llmLogs({ kind: logKind || undefined, limit: 40 })
      .then(setLogs)
      .catch((e: Error) => setError(e.message));
  }, [openPanel, logKind, setError]);

  async function run(action: () => Promise<unknown>, okMsg: string) {
    setBusy(true);
    setNote("");
    try {
      await action();
      await reload();
      setNote(okMsg);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function addCat() {
    const name = newCat.trim();
    if (!name) return;
    await run(async () => {
      const cat = await api.addCategory(name);
      setCategories((prev) => {
        if (prev.some((c) => c.id === cat.id)) return prev;
        return [...prev, cat].sort(
          (a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name),
        );
      });
      setNewCat("");
    }, "Category added. Applies to new extractions only.");
  }

  async function toggleDeprecated(cat: Category) {
    await run(async () => {
      const updated = await api.patchCategory(cat.id, { deprecated: !cat.deprecated });
      setCategories((prev) => prev.map((c) => (c.id === cat.id ? updated : c)));
    }, "Category updated. Old assignments are unchanged.");
  }

  if (!ctx) {
    return <p className="job-idle">Loading research context…</p>;
  }

  const ingestTip =
    "Optional test feature: paste a blog/GitHub URL (or upload a PDF for probes) and the LLM drafts a title plus a 2–3 sentence description from the page text. Images and video are not supported. You can always type title and description manually instead.";

  return (
    <div className="admin-view">
      <div className="admin-banner" role="status">
        <strong>Changes apply to new newsletters only.</strong> Editing research context or
        categories does not re-analyse emails already in the database and never wipes marks or
        comments. Open a panel below to edit that section.
      </div>
      {error && <p className="err">{error}</p>}
      {note && <p className="admin-saved">{note}</p>}

      <AdminPanel
        id="priorities"
        title="Higher-priority research areas"
        count={ctx.priority_areas.length}
        openId={openPanel}
        setOpenId={setOpenPanel}
      >
        <p className="admin-panel-lead">
          Name and description are separate fields. Matching candidates can be tagged High
          Priority when they also have a hands-on path.
        </p>
        <ul className="admin-item-list">
          {ctx.priority_areas.map((p: ResearchPriority) => (
            <li key={p.id}>
              <details>
                <summary>{p.name}</summary>
                <textarea
                  rows={4}
                  defaultValue={p.description}
                  aria-label={`${p.name} description`}
                  onBlur={(e) => {
                    if (e.target.value === p.description) return;
                    run(
                      () => api.patchPriority(p.id, { description: e.target.value }),
                      "Priority updated.",
                    );
                  }}
                />
                <input
                  defaultValue={p.name}
                  aria-label={`${p.name} title`}
                  onBlur={(e) => {
                    if (e.target.value.trim() === p.name) return;
                    run(
                      () => api.patchPriority(p.id, { name: e.target.value }),
                      "Priority renamed.",
                    );
                  }}
                />
                <button
                  type="button"
                  className="btn-quiet"
                  disabled={busy}
                  onClick={() =>
                    run(() => api.deletePriority(p.id), "Priority removed from future prompts.")
                  }
                >
                  Remove
                </button>
              </details>
            </li>
          ))}
        </ul>
        <form
          className="admin-add-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (!priName.trim()) return;
            run(async () => {
              await api.createPriority({ name: priName, description: priDesc });
              setPriName("");
              setPriDesc("");
            }, "Priority added.");
          }}
        >
          <input
            value={priName}
            onChange={(e) => setPriName(e.target.value)}
            placeholder="Area name"
            aria-label="New priority name"
          />
          <textarea
            rows={2}
            value={priDesc}
            onChange={(e) => setPriDesc(e.target.value)}
            placeholder="Description"
            aria-label="New priority description"
          />
          <button type="submit" className="btn-primary" disabled={busy || !priName.trim()}>
            Add area
          </button>
        </form>
      </AdminPanel>

      <AdminPanel
        id="probes"
        title="Previous Genie probes"
        count={ctx.probes.length}
        openId={openPanel}
        setOpenId={setOpenPanel}
      >
        <p className="admin-panel-lead">
          Short descriptions of past hands-on investigations.{" "}
          <InfoTip text={ingestTip} />
        </p>
        <ul className="admin-item-list">
          {ctx.probes.map((p: ResearchItem) => (
            <li key={p.id}>
              <details>
                <summary>
                  {p.title}
                  {p.source_kind !== "manual" ? (
                    <span className="admin-source-tag">{p.source_kind}</span>
                  ) : null}
                </summary>
                <textarea
                  rows={4}
                  defaultValue={p.description}
                  onBlur={(e) => {
                    if (e.target.value === p.description) return;
                    run(
                      () => api.patchProbe(p.id, { description: e.target.value }),
                      "Probe updated.",
                    );
                  }}
                />
                <input
                  defaultValue={p.title}
                  onBlur={(e) => {
                    if (e.target.value.trim() === p.title) return;
                    run(() => api.patchProbe(p.id, { title: e.target.value }), "Probe renamed.");
                  }}
                />
                {p.source_url && <p className="meta">Source: {p.source_url}</p>}
                <button
                  type="button"
                  className="btn-quiet"
                  disabled={busy}
                  onClick={() => run(() => api.deleteProbe(p.id), "Probe removed.")}
                >
                  Remove
                </button>
              </details>
            </li>
          ))}
        </ul>
        <form
          className="admin-add-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (!probeTitle.trim()) return;
            run(async () => {
              await api.createProbe({ title: probeTitle, description: probeDesc });
              setProbeTitle("");
              setProbeDesc("");
            }, "Probe added manually.");
          }}
        >
          <p className="field-label">Add manually</p>
          <input
            value={probeTitle}
            onChange={(e) => setProbeTitle(e.target.value)}
            placeholder="Title"
          />
          <textarea
            rows={2}
            value={probeDesc}
            onChange={(e) => setProbeDesc(e.target.value)}
            placeholder="2–3 sentence description"
          />
          <button type="submit" className="btn-primary" disabled={busy || !probeTitle.trim()}>
            Add probe
          </button>
        </form>
        <div className="admin-ingest">
          <p className="field-label">
            Or draft from a PDF / URL <InfoTip text={ingestTip} />
          </p>
          <div className="admin-ingest-row">
            <input
              value={probeUrl}
              onChange={(e) => setProbeUrl(e.target.value)}
              placeholder="https://… blog or docs page"
              aria-label="Probe source URL"
            />
            <button
              type="button"
              className="btn-primary"
              disabled={busy || !probeUrl.trim()}
              onClick={() =>
                run(async () => {
                  await api.ingestProbeUrl(probeUrl.trim());
                  setProbeUrl("");
                }, "Probe drafted from URL and saved. Review the text in the list.")
              }
            >
              Analyse URL
            </button>
          </div>
          <label className="admin-file">
            Upload PDF
            <input
              type="file"
              accept="application/pdf,.pdf"
              disabled={busy}
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (!file) return;
                run(
                  () => api.ingestProbePdf(file),
                  "Probe drafted from PDF and saved. Review the text in the list.",
                );
              }}
            />
          </label>
        </div>
      </AdminPanel>

      <AdminPanel
        id="artifacts"
        title="Related Genie artifacts"
        count={ctx.artifacts.length}
        openId={openPanel}
        setOpenId={setOpenPanel}
      >
        <p className="admin-panel-lead">
          Guides, architectures, and other Genie work the scout should know about.{" "}
          <InfoTip text={ingestTip} />
        </p>
        <ul className="admin-item-list">
          {ctx.artifacts.map((a: ResearchItem) => (
            <li key={a.id}>
              <details>
                <summary>
                  {a.title}
                  {a.source_kind !== "manual" ? (
                    <span className="admin-source-tag">{a.source_kind}</span>
                  ) : null}
                </summary>
                <textarea
                  rows={4}
                  defaultValue={a.description}
                  onBlur={(e) => {
                    if (e.target.value === a.description) return;
                    run(
                      () => api.patchArtifact(a.id, { description: e.target.value }),
                      "Artifact updated.",
                    );
                  }}
                />
                <input
                  defaultValue={a.title}
                  onBlur={(e) => {
                    if (e.target.value.trim() === a.title) return;
                    run(
                      () => api.patchArtifact(a.id, { title: e.target.value }),
                      "Artifact renamed.",
                    );
                  }}
                />
                {a.source_url && <p className="meta">Source: {a.source_url}</p>}
                <button
                  type="button"
                  className="btn-quiet"
                  disabled={busy}
                  onClick={() => run(() => api.deleteArtifact(a.id), "Artifact removed.")}
                >
                  Remove
                </button>
              </details>
            </li>
          ))}
        </ul>
        <form
          className="admin-add-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (!artTitle.trim()) return;
            run(async () => {
              await api.createArtifact({ title: artTitle, description: artDesc });
              setArtTitle("");
              setArtDesc("");
            }, "Artifact added manually.");
          }}
        >
          <p className="field-label">Add manually</p>
          <input
            value={artTitle}
            onChange={(e) => setArtTitle(e.target.value)}
            placeholder="Title"
          />
          <textarea
            rows={2}
            value={artDesc}
            onChange={(e) => setArtDesc(e.target.value)}
            placeholder="2–3 sentence description"
          />
          <button type="submit" className="btn-primary" disabled={busy || !artTitle.trim()}>
            Add artifact
          </button>
        </form>
        <div className="admin-ingest">
          <p className="field-label">
            Or draft from a URL <InfoTip text={ingestTip} />
          </p>
          <div className="admin-ingest-row">
            <input
              value={artUrl}
              onChange={(e) => setArtUrl(e.target.value)}
              placeholder="https://… blog, GitHub, docs"
              aria-label="Artifact source URL"
            />
            <button
              type="button"
              className="btn-primary"
              disabled={busy || !artUrl.trim()}
              onClick={() =>
                run(async () => {
                  await api.ingestArtifactUrl(artUrl.trim());
                  setArtUrl("");
                }, "Artifact drafted from URL and saved.")
              }
            >
              Analyse URL
            </button>
          </div>
        </div>
      </AdminPanel>

      <AdminPanel
        id="not-useful"
        title="Generally not useful"
        count={ctx.not_useful.length}
        openId={openPanel}
        setOpenId={setOpenPanel}
      >
        <ul className="admin-item-list">
          {ctx.not_useful.map((n: ResearchNotUseful) => (
            <li key={n.id} className="admin-inline-row">
              <input
                defaultValue={n.text}
                onBlur={(e) => {
                  if (e.target.value.trim() === n.text) return;
                  run(
                    () => api.patchNotUseful(n.id, e.target.value),
                    "Not-useful item updated.",
                  );
                }}
              />
              <button
                type="button"
                className="btn-quiet"
                disabled={busy}
                onClick={() => run(() => api.deleteNotUseful(n.id), "Item removed.")}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
        <form
          className="admin-add-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (!nuText.trim()) return;
            run(async () => {
              await api.createNotUseful(nuText);
              setNuText("");
            }, "Item added.");
          }}
        >
          <input
            value={nuText}
            onChange={(e) => setNuText(e.target.value)}
            placeholder="e.g. funding or market dynamics"
          />
          <button type="submit" className="btn-primary" disabled={busy || !nuText.trim()}>
            Add
          </button>
        </form>
      </AdminPanel>

      <AdminPanel
        id="categories"
        title="Categories"
        count={categories.length}
        openId={openPanel}
        setOpenId={setOpenPanel}
      >
        <p className="admin-panel-lead">
          New categories and deprecations affect <strong>new</strong> extractions only. Old
          candidates keep their existing category.
        </p>
        <ul className="admin-cat-list">
          {categories.map((cat) => (
            <li key={cat.id} className={cat.deprecated ? "deprecated" : ""}>
              <span>
                {cat.name}
                {cat.deprecated ? " · deprecated" : ""}
              </span>
              <button
                type="button"
                className="btn-quiet"
                disabled={busy}
                onClick={() => toggleDeprecated(cat)}
              >
                {cat.deprecated ? "Restore for new mail" : "Deprecate for new mail"}
              </button>
            </li>
          ))}
        </ul>
        <form
          className="new-cat-form"
          onSubmit={(e) => {
            e.preventDefault();
            addCat();
          }}
        >
          <input
            value={newCat}
            onChange={(e) => setNewCat(e.target.value)}
            placeholder="New category name"
            aria-label="New category name"
          />
          <button type="submit" disabled={busy || !newCat.trim()}>
            Add category
          </button>
        </form>
      </AdminPanel>

      <AdminPanel
        id="prompt"
        title="Live prompt preview"
        openId={openPanel}
        setOpenId={setOpenPanel}
      >
        <p className="admin-panel-lead">
          Exact research-context block currently composed for the extractor (from the database).
        </p>
        <pre className="admin-pre">{ctx.prompt_preview}</pre>
      </AdminPanel>

      <AdminPanel
        id="logs"
        title="LLM call logs"
        count={logs.length}
        openId={openPanel}
        setOpenId={setOpenPanel}
      >
        <p className="admin-panel-lead">
          Instructions, newsletter (or source text), and model output are stored separately for
          each call.
        </p>
        <div className="segmented">
          {[
            { id: "extract", label: "Extractions" },
            { id: "probe_ingest", label: "Probe ingest" },
            { id: "artifact_ingest", label: "Artifact ingest" },
            { id: "", label: "All" },
          ].map((opt) => (
            <button
              key={opt.id || "all"}
              type="button"
              className={logKind === opt.id ? "on" : ""}
              onClick={() => setLogKind(opt.id)}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <ul className="admin-log-list">
          {logs.map((log) => (
            <li key={log.id}>
              <button
                type="button"
                className="admin-log-row"
                onClick={() =>
                  api
                    .llmLog(log.id)
                    .then(setLogDetail)
                    .catch((e: Error) => setError(e.message))
                }
              >
                <span className="admin-log-kind">{log.kind}</span>
                <span className="admin-log-when">
                  {log.created_at ? new Date(log.created_at).toLocaleString() : ""}
                </span>
                <span className="admin-log-preview">{log.input_preview || "—"}</span>
              </button>
            </li>
          ))}
          {logs.length === 0 && <li className="meta">No logs yet for this filter.</li>}
        </ul>
      </AdminPanel>

      {logDetail && (
        <>
          <div className="email-backdrop" onClick={() => setLogDetail(null)} />
          <div className="comment-modal admin-log-modal">
            <h2>LLM call #{logDetail.id}</h2>
            <p className="meta">
              {logDetail.kind}
              {logDetail.email_id ? ` · email ${logDetail.email_id}` : ""}
              {logDetail.model ? ` · ${logDetail.model}` : ""}
              {logDetail.created_at
                ? ` · ${new Date(logDetail.created_at).toLocaleString()}`
                : ""}
            </p>
            <div className="admin-log-section">
              <h3>Instructions</h3>
              <pre className="admin-pre">{logDetail.instructions_text}</pre>
            </div>
            <div className="admin-log-section">
              <h3>Input (newsletter or source)</h3>
              <pre className="admin-pre">{logDetail.input_text}</pre>
            </div>
            <div className="admin-log-section">
              <h3>Model output</h3>
              <pre className="admin-pre">{formatJsonish(logDetail.output_text)}</pre>
            </div>
            <button type="button" className="btn-primary" onClick={() => setLogDetail(null)}>
              Close
            </button>
          </div>
        </>
      )}
    </div>
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

/** Which mailbox the newsletters are forwarded to, and whether the daily pull is on. */
function InboxStatus({ settings }: { settings: SettingsStatus | null }) {
  if (!settings) {
    return <span className="inbox-chip">Checking inbox…</span>;
  }
  if (!settings.inbox_configured) {
    return <span className="inbox-chip warn">Set up the dedicated inbox in .env</span>;
  }
  const schedule = settings.inbox_enabled
    ? `auto daily at ${syncHourLabel(settings.sync_hour)}`
    : "daily pull off";
  return (
    <span
      className={`inbox-chip ${settings.inbox_enabled ? "ok" : "warn"}`}
      title={`${settings.inbox_host} · ${settings.inbox_folder}${
        settings.allowed_from.length ? ` · from ${settings.allowed_from.join(", ")}` : ""
      }`}
    >
      Inbox · {settings.inbox_email || "configured"} · {schedule}
    </span>
  );
}
