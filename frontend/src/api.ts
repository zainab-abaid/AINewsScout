export type TagSlug = "high-priority" | "strong" | "possible";

export type PublishStatus = {
  status: "idle" | "running" | "done" | "error";
  url: string;
  error: string;
};

export type Candidate = {
  id: number;
  email_id: number;
  tag: string;
  tag_slug: TagSlug | string;
  topic: string;
  main_idea: string;
  excerpt: string;
  important: boolean;
  shortlisted: boolean;
  deleted: boolean;
  processed: boolean;
  category_id: number | null;
  category_name: string;
  notes: string;
  marked_at: string;
  email_title: string;
  email_date: string;
  date_iso: string;
  from_addr: string;
};

export type Category = {
  id: number;
  name: string;
  is_default: boolean;
  sort_order: number;
};

export type Stats = {
  emails: number;
  emails_with_candidates: number;
  emails_pending_extraction: number;
  candidates: number;
  high_priority: number;
  strong: number;
  possible: number;
  important: number;
  shortlisted: number;
  deleted: number;
  unprocessed: number;
  date_from: string | null;
  date_to: string | null;
};

export type Job = {
  id: number;
  kind: string;
  status: string;
  payload: Record<string, unknown>;
  progress: Record<string, unknown>;
  error: string | null;
  created_at: string;
  finished_at: string | null;
};

export type SyncPreview = {
  date_from: string | null;
  date_to: string | null;
  stored: number;
  extracted: number;
  pending: number;
  failed: number;
  candidates: number;
  marked: number;
  needs_confirm: boolean;
};

export type SettingsStatus = {
  connected: boolean;
  email: string | null;
  has_client: boolean;
  redirect_uri: string;
  label: string;
  openai_configured: boolean;
};

export type EmailDetail = {
  id: number;
  subject: string;
  from_addr: string;
  date_raw: string;
  date_iso: string;
  body_md: string;
  extraction_status: string;
  extraction_error: string | null;
};

export type SearchHit = {
  id: number;
  email_id: number;
  relevance: string;
  title: string;
  excerpt: string;
  why_relevant: string;
  email_title: string;
  email_date: string;
  date_iso: string;
  candidate_id: number | null;
};

export type IdeaSearch = {
  id: number;
  question: string;
  date_from: string | null;
  date_to: string | null;
  status: string;
  emails_total: number;
  chunks_total: number;
  chunks_done: number;
  chunks_failed: number;
  hits_total: number;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  phase: string;
  listed: number;
  new_emails: number;
  skipped: number;
  current: number;
};

export type IdeaSearchDetail = IdeaSearch & { hits: SearchHit[] };

export type SearchPreview = {
  date_from: string | null;
  date_to: string | null;
  emails: number;
  stored: number;
  will_fetch: number;
  gmail_connected: boolean;
  gmail_checked: boolean;
  chunks: number;
};

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  stats: () => http<Stats>("/api/stats"),
  candidates: (params: Record<string, string> = {}) => {
    const q = new URLSearchParams(params);
    return http<Candidate[]>(`/api/candidates?${q.toString()}`);
  },
  patchCandidate: (id: number, body: Record<string, unknown>) =>
    http<Candidate>(`/api/candidates/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  categories: () => http<Category[]>("/api/categories"),
  addCategory: (name: string) =>
    http<Category>("/api/categories", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  email: (id: number) => http<EmailDetail>(`/api/emails/${id}`),
  settings: () => http<SettingsStatus>("/api/settings/status"),
  connectUrl: () => http<{ auth_url: string }>("/api/gmail/connect"),
  disconnect: () => http<SettingsStatus>("/api/gmail/disconnect", { method: "POST" }),
  sync: (body: {
    date_from?: string;
    date_to?: string;
    label?: string;
    extract?: boolean;
    overwrite_extracted?: boolean;
  }) => http<Job>("/api/sync", { method: "POST", body: JSON.stringify(body) }),
  syncPreview: (body: { date_from?: string; date_to?: string }) =>
    http<SyncPreview>("/api/sync/preview", { method: "POST", body: JSON.stringify(body) }),
  extract: () => http<Job>("/api/extract", { method: "POST", body: JSON.stringify({ pending_only: true }) }),
  job: (id: number) => http<Job>(`/api/jobs/${id}`),
  searchPreview: (body: { question?: string; date_from?: string; date_to?: string }) =>
    http<SearchPreview>("/api/searches/preview", {
      method: "POST",
      body: JSON.stringify({ question: "", ...body }),
    }),
  createSearch: (body: { question: string; date_from?: string; date_to?: string }) =>
    http<IdeaSearch>("/api/searches", { method: "POST", body: JSON.stringify(body) }),
  searches: () => http<IdeaSearch[]>("/api/searches"),
  search: (id: number) => http<IdeaSearchDetail>(`/api/searches/${id}`),
  keepHit: (
    searchId: number,
    hitId: number,
    body: {
      tag: string;
      category_id?: number;
      notes?: string;
      important?: boolean;
      shortlisted?: boolean;
    },
  ) =>
    http<{ hit: SearchHit; candidate: Candidate }>(
      `/api/searches/${searchId}/hits/${hitId}/keep`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  deleteSearch: (id: number) =>
    http<{ ok: boolean }>(`/api/searches/${id}`, { method: "DELETE" }),
  publishStatus: () => http<PublishStatus>("/api/publish"),
  publish: () => http<PublishStatus>("/api/publish", { method: "POST" }),
  activeJob: async () => {
    const res = await fetch("/api/jobs/active", {
      headers: { "Content-Type": "application/json" },
    });
    if (!res.ok) throw new Error(res.statusText);
    const body = await res.json();
    return (body as Job | null) ?? null;
  },
};
