import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type Candidate,
  type Category,
  type EmailDetail,
  type Job,
  type SettingsStatus,
  type Stats,
  type SyncPreview,
} from "./api";
import { MarkdownBody, MarkdownInline } from "./markdown";
import {
  UNCATEGORISED,
  allCategoriesOn,
  filterCandidates,
  filtersAreDefault,
  hideAllCategories,
  isCategoryOn,
  onCategoryCount,
  showAllCategories,
  toggleCategoryVisibility,
  type MarkFilter,
  type TagFilter,
} from "./filters";

const TAG_OPTIONS: { id: TagFilter; label: string }[] = [
  { id: "high-priority", label: "High priority" },
  { id: "strong", label: "Strong" },
  { id: "possible", label: "Possible" },
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
  const [email, setEmail] = useState<EmailDetail | null>(null);
  const [emailExcerpt, setEmailExcerpt] = useState("");
  const [emailLoading, setEmailLoading] = useState(false);
  const [syncFrom, setSyncFrom] = useState("");
  const [syncTo, setSyncTo] = useState(todayIso());
  const [now, setNow] = useState(Date.now());
  const [syncConfirm, setSyncConfirm] = useState<SyncPreview | null>(null);
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

  async function patch(id: number, body: Record<string, unknown>) {
    const updated = await api.patchCandidate(id, body);
    setCandidates((prev) => prev.map((c) => (c.id === id ? updated : c)));
    const s = await api.stats();
    setStats(s);
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

  const range =
    stats?.date_from && stats?.date_to ? `${stats.date_from} – ${stats.date_to}` : "Local corpus";
  const showJob = job && job.id !== dismissedJobId;

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>Probe scout</h1>
          <p className="header-meta">
            {range}
            {stats ? ` · ${stats.unprocessed} unprocessed` : ""}
          </p>
        </div>
        <div className="header-right">
          <GmailControl settings={settings} onChange={setSettings} setError={setError} />
        </div>
      </header>

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
                  Marked important by user, shortlisted by user, or deleted
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
                />
              ))
            )}
          </main>
        </>

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
}: {
  c: Candidate;
  categories: Category[];
  onPatch: (id: number, body: Record<string, unknown>) => Promise<void>;
  onAddCategory: (name: string) => Promise<Category>;
  onOpenEmail: (id: number, excerpt: string) => void;
}) {
  const [addingCategory, setAddingCategory] = useState(false);
  const cls = [
    "candidate-card",
    c.important ? "is-important" : "",
    c.shortlisted ? "is-shortlisted" : "",
    c.deleted ? "is-deleted" : "",
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
          {c.deleted && <span className="badge deleted-flag">Deleted</span>}
        </div>
        <div className="card-actions">
          {addingCategory ? (
            <NewCategoryForm
              onSave={async (name) => {
                const cat = await onAddCategory(name);
                await onPatch(c.id, { category_id: cat.id });
                setAddingCategory(false);
              }}
              onCancel={() => setAddingCategory(false)}
            />
          ) : (
            <select
              value={c.category_id ?? ""}
              onChange={async (e) => {
                if (e.target.value === "__new__") {
                  setAddingCategory(true);
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
          )}
          <button
            type="button"
            className={`btn-important ${c.important ? "is-on" : ""}`}
            onClick={() => onPatch(c.id, { important: !c.important })}
          >
            {c.important ? "Remove user-important mark" : "Mark important (user)"}
          </button>
          <button
            type="button"
            className={`btn-shortlist ${c.shortlisted ? "is-on" : ""}`}
            onClick={() => onPatch(c.id, { shortlisted: !c.shortlisted })}
          >
            {c.shortlisted ? "Remove user shortlist" : "Shortlist (user)"}
          </button>
          <button type="button" className="btn-delete" onClick={() => onPatch(c.id, { deleted: !c.deleted })}>
            {c.deleted ? "Undelete" : "Delete"}
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
    </article>
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
