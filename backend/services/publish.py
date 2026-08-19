"""Generate a self-contained read-only index.html from the local DB and push
it to the public GitHub Pages repo (zainab-abaid/ainews_public_view).

The page embeds all data as a JSON blob so it works without a server.
Email bodies are embedded too so the open/scroll feature works offline.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlmodel import select

from backend.config import ROOT
from backend.database import session_scope
from backend.db import Candidate, Category, Email
from backend.services.links import hydrate_excerpt_links, normalize_inline_links

PUBLIC_REPO = "https://github.com/zainab-abaid/ainews_public_view.git"
_CLONE_DIR = ROOT / "data" / "_publish_clone"


# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------

def _iso(dt: Optional[datetime]) -> str:
    return dt.strftime("%Y-%m-%d") if dt else ""


def _iso_dt(dt: Optional[datetime]) -> str:
    return dt.isoformat() if dt else ""


def _build_payload() -> dict[str, Any]:
    with session_scope() as session:
        cats = session.exec(select(Category).order_by(Category.sort_order, Category.name)).all()
        cat_by_id = {c.id: c.name for c in cats if c.id is not None}
        categories = [c.name for c in cats]

        emails_q = session.exec(select(Email)).all()
        email_by_id = {e.id: e for e in emails_q if e.id is not None}

        cands = session.exec(select(Candidate)).all()
        items: list[dict] = []
        for c in cands:
            if c.deleted:
                continue
            em = email_by_id.get(c.email_id)
            if em is None:
                continue
            items.append({
                "id": c.id,
                "email_id": c.email_id,
                "topic": c.topic,
                "main_idea": c.main_idea,
                "excerpt": hydrate_excerpt_links(c.excerpt, em.body_md),
                "important": c.important,
                "shortlisted": c.shortlisted,
                "category": cat_by_id.get(c.category_id, "") if c.category_id else "",
                "notes": c.notes or "",
                "marked_at": _iso_dt(c.marked_at),
                "email_title": em.subject,
                "email_date": em.date_raw or _iso(em.sent_at),
                "date_iso": _iso(em.sent_at),
            })

        emails_out: dict[int, dict] = {}
        for eid, em in email_by_id.items():
            emails_out[eid] = {
                "subject": em.subject,
                "date_raw": em.date_raw,
                "date_iso": _iso(em.sent_at),
                "body_md": normalize_inline_links(em.body_md),
            }

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return {
        "generated_at": generated_at,
        "categories": categories,
        "items": items,
        "emails": {str(k): v for k, v in emails_out.items()},
    }


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI News Newsletter Explorer</title>
<script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
<style>
:root{--bg:#f4f1ea;--ink:#1a1a1a;--muted:#5c5c5c;--card:#fff;--border:#ddd6cb;
  --important:#0f6b4c;--important-bg:#e3f5ee;--shortlist:#6b3fa0;--shortlist-bg:#f0e8fa;
  --track:#e8e2d6}
*{box-sizing:border-box}
body{margin:0;font-family:"IBM Plex Sans","Segoe UI",sans-serif;background:var(--bg);
  color:var(--ink);line-height:1.5}
.shell{max-width:1060px;margin:0 auto;padding:0 1.25rem 3rem}
header{padding:1.4rem 0 .9rem;border-bottom:1px solid var(--border);margin-bottom:1rem;
  display:flex;flex-wrap:wrap;align-items:baseline;gap:.5rem 1rem}
header h1{margin:0;font-size:1.3rem;font-weight:700;letter-spacing:-.02em}
.gen-at{font-size:.82rem;color:var(--muted)}
nav{display:flex;gap:.3rem;margin-bottom:1rem;flex-wrap:wrap}
nav button{font:inherit;font-size:.92rem;cursor:pointer;padding:.35rem .85rem;
  border-radius:8px;border:1px solid var(--border);background:var(--bg);color:var(--muted)}
nav button.on{background:var(--card);color:var(--ink);font-weight:650;border-color:var(--ink)}
.controls{display:flex;flex-wrap:wrap;gap:.7rem 1rem;align-items:flex-start;margin-bottom:.9rem}
.date-group{display:flex;gap:.5rem;align-items:center}
.date-group label{font-size:.85rem;color:var(--muted);display:flex;align-items:center;gap:.3rem}
.date-group input[type=date]{font:inherit;font-size:.88rem;padding:.3rem .55rem;
  border:1px solid var(--border);border-radius:8px;background:var(--card)}
.cat-group{display:flex;flex-direction:column;gap:.25rem}
.cat-group-label{font-size:.82rem;font-weight:600;color:var(--muted);margin-bottom:.1rem}
.cat-checks{display:flex;flex-wrap:wrap;gap:.25rem .6rem}
.cat-checks label{font-size:.83rem;color:var(--ink);display:flex;align-items:center;gap:.25rem;cursor:pointer}
.btn-pdf{font:inherit;font-size:.88rem;cursor:pointer;padding:.35rem .85rem;
  border-radius:8px;border:1px solid var(--border);background:var(--ink);color:#fff;
  font-weight:650;align-self:flex-end;margin-left:auto}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;
  padding:1rem 1.1rem;margin-bottom:.75rem}
.card h2{margin:0 0 .2rem;font-size:1rem;font-weight:650}
.meta-lines{margin:0 0 .55rem}
.news-title-btn{all:unset;cursor:pointer;color:var(--ink);text-decoration:underline;
  text-underline-offset:3px;font-weight:650}
.news-date{font-size:.82rem;color:var(--muted);margin-top:.15rem}
.item-category{font-size:.88rem;margin-top:.15rem}
.item-category-label{font-weight:700;color:var(--muted);margin-right:.35rem}
.card .md-block{font-size:.9rem;margin:.5rem 0 0;border-left:3px solid var(--border);
  padding-left:.75rem}
.card .md-block p{margin:.2rem 0}
.card .md-block a{color:var(--ink)}
.card .notes{font-size:.85rem;color:var(--muted);margin:.6rem 0 0;font-style:italic;
  border-left:3px solid var(--shortlist-bg);padding-left:.6rem}
.badge{display:inline-block;font-size:.72rem;font-weight:700;letter-spacing:.04em;
  text-transform:uppercase;border-radius:4px;padding:.1rem .45rem;margin:.1rem .2rem .1rem 0}
.b-imp{background:var(--important-bg);color:var(--important)}
.b-short{background:var(--shortlist-bg);color:var(--shortlist)}
.empty{color:var(--muted);font-size:.95rem;padding:1.5rem 0}

/* email modal */
.backdrop{position:fixed;inset:0;background:rgba(0,0,0,.3);z-index:10}
.email-modal{position:fixed;inset:5vh 6vw;overflow:auto;z-index:11;
  background:var(--card);border-radius:12px;padding:1.25rem 1.5rem;
  box-shadow:0 18px 50px rgba(0,0,0,.22)}
.email-modal h2{margin:0 0 .5rem;font-size:1.1rem}
.close-btn{position:sticky;top:0;float:right;font:inherit;font-size:1.2rem;cursor:pointer;
  border:0;background:none;color:var(--muted);padding:0 .2rem}
.email-body{white-space:normal;font-size:.93rem;line-height:1.55;max-width:46rem;margin-top:.5rem}
.email-body h1{font-size:1.3rem;margin:.1rem 0 .5rem}
.email-body h2{font-size:1.1rem;margin:1rem 0 .35rem}
.email-body h3{font-size:1rem;margin:.9rem 0 .3rem}
.email-body p{margin:0 0 .8rem}
.email-body ul{margin:0 0 .8rem;padding-left:1.2rem}
.email-body li{margin:.15rem 0}
.email-body hr{border:0;border-top:1px solid var(--border);margin:.9rem 0}
.email-body a{color:var(--ink)}
mark.highlight{background:#fff176;border-radius:3px}

@media print{
  header,nav,.controls{display:none!important}
  .btn-pdf{display:none!important}
  .backdrop,.email-modal{display:none!important}
  .card{break-inside:avoid;border:1px solid #ccc;margin-bottom:.5rem}
}
</style>
</head>
<body>
<div class="shell">
  <header>
    <h1>AI News Newsletter Explorer</h1>
    <span class="gen-at">Snapshot: __GENERATED_AT__</span>
  </header>

  <nav id="tabs">
    <button class="on" data-tab="all" onclick="switchTab('all')">All extracted items</button>
    <button data-tab="important" onclick="switchTab('important')">Marked important</button>
    <button data-tab="shortlisted" onclick="switchTab('shortlisted')">Shortlisted for probe</button>
  </nav>

  <div class="controls">
    <div class="cat-group">
      <div class="cat-group-label">Categories</div>
      <div class="cat-checks" id="cat-checks"></div>
    </div>
    <div class="date-group">
      <label>From <input type="date" id="date-from" onchange="render()"></label>
      <label>To <input type="date" id="date-to" onchange="render()"></label>
    </div>
    <button class="btn-pdf" onclick="window.print()">Download PDF</button>
  </div>

  <div id="list"></div>
</div>

<!-- email modal -->
<div id="backdrop" class="backdrop" style="display:none" onclick="closeEmail()"></div>
<div id="email-modal" class="email-modal" style="display:none">
  <button class="close-btn" onclick="closeEmail()">✕</button>
  <h2 id="modal-title"></h2>
  <div id="modal-body" class="email-body"></div>
</div>

<script>
const DATA = __JSON_DATA__;

let currentTab = 'all';
// item id → item lookup so onclick handlers don't embed data in attributes
const ITEM_MAP = {};
DATA.items.forEach(item => { ITEM_MAP[item.id] = item; });

const dateFrom = document.getElementById('date-from');
const dateTo = document.getElementById('date-to');

// Build category checkboxes (multi-select).
const catChecksEl = document.getElementById('cat-checks');
DATA.categories.forEach(c => {
  const lbl = document.createElement('label');
  const cb = document.createElement('input');
  cb.type = 'checkbox'; cb.value = c; cb.addEventListener('change', render);
  lbl.appendChild(cb);
  lbl.appendChild(document.createTextNode(' ' + c));
  catChecksEl.appendChild(lbl);
});

function selectedCats() {
  return Array.from(catChecksEl.querySelectorAll('input:checked')).map(el => el.value);
}

function switchTab(t) {
  currentTab = t;
  document.querySelectorAll('#tabs button').forEach(b =>
    b.classList.toggle('on', b.dataset.tab === t));
  render();
}

function mdInline(text) {
  // Render markdown but strip outer <p> tags so it stays inline-ish.
  const html = marked.parse(String(text || ''), {breaks: true});
  return html.replace(/^<p>([\s\S]*?)<\/p>\s*$/, '$1').trim();
}

function render() {
  const cats = selectedCats();
  const from = dateFrom.value;
  const to = dateTo.value;
  let items = DATA.items.filter(item => {
    if (currentTab === 'important' && !item.important) return false;
    if (currentTab === 'shortlisted' && !item.shortlisted) return false;
    if (cats.length && !cats.includes(item.category)) return false;
    if (from && item.date_iso && item.date_iso < from) return false;
    if (to && item.date_iso && item.date_iso > to) return false;
    return true;
  });
  items.sort((a, b) => {
    if (a.date_iso !== b.date_iso) return a.date_iso < b.date_iso ? 1 : -1;
    return a.topic.localeCompare(b.topic);
  });
  const list = document.getElementById('list');
  if (!items.length) {
    list.innerHTML = '<p class="empty">No items match the current filters.</p>';
    return;
  }
  list.innerHTML = items.map(item => {
    const badges = [
      item.important ? '<span class="badge b-imp">Important</span>' : '',
      item.shortlisted ? '<span class="badge b-short">Shortlisted for probe</span>' : '',
    ].join('');
    const catLabel = item.category
      ? `<span style="color:var(--muted);margin-left:.3rem">· ${esc(item.category)}</span>` : '';
    const notes = item.notes && item.notes.trim()
      ? `<p class="notes">${esc(item.notes)}</p>` : '';
    const categoryDisplay = item.category ? esc(item.category) : '(none)';
    return `<div class="card">
      <h2>${esc(item.topic)}</h2>
      <div class="meta-lines">
        <div class="news-title">
          <button class="news-title-btn" data-item-id="${item.id}">${esc(item.email_title)}</button>
        </div>
        <div class="news-date">${esc(item.email_date)}</div>
        <div class="item-category">
          <span class="item-category-label">Category:</span> ${categoryDisplay}
        </div>
      </div>
      ${badges}
      <div class="md-block">${mdInline(item.main_idea)}</div>
      <div class="md-block">${mdInline(item.excerpt)}</div>
      ${notes}
    </div>`;
  }).join('');

  // Attach click handlers to email buttons (avoids embedding data in onclick attrs).
  list.querySelectorAll('button[data-item-id]').forEach(btn => {
    btn.addEventListener('click', () => {
      const item = ITEM_MAP[Number(btn.dataset.itemId)];
      if (item) openEmail(item.email_id, item.excerpt);
    });
  });
}

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function openEmail(emailId, excerpt) {
  const em = DATA.emails[String(emailId)];
  if (!em) return;
  document.getElementById('modal-title').textContent = em.subject;
  const bodyEl = document.getElementById('modal-body');
  bodyEl.innerHTML = marked.parse(em.body_md || '', {breaks: true});
  document.getElementById('backdrop').style.display = '';
  document.getElementById('email-modal').style.display = '';
  document.body.style.overflow = 'hidden';

  // Strip markdown syntax from excerpt to get plain words for matching.
  const plainExcerpt = String(excerpt || '').replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[*_`#]/g, '');
  setTimeout(() => scrollToExcerpt(bodyEl, plainExcerpt), 80);
}

function scrollToExcerpt(container, excerpt) {
  const words = excerpt.trim().split(/\s+/).filter(Boolean).slice(0, 8);
  if (!words.length) return;
  // Try progressively shorter prefixes until we find a match.
  for (let len = words.length; len >= 3; len--) {
    const pattern = words.slice(0, len)
      .map(w => w.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('[\\s\\S]{0,4}');
    const re = new RegExp(pattern, 'i');
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const m = node.textContent.search(re);
      if (m < 0) continue;
      try {
        const range = document.createRange();
        const end = Math.min(node.textContent.length, m + 200);
        range.setStart(node, m);
        range.setEnd(node, end);
        const mark = document.createElement('mark');
        mark.className = 'highlight';
        range.surroundContents(mark);
        mark.scrollIntoView({ behavior: 'smooth', block: 'center' });
      } catch { /* node boundary edge case – skip */ }
      return;
    }
  }
  // Fallback: scroll to top of modal.
  container.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function closeEmail() {
  document.getElementById('backdrop').style.display = 'none';
  document.getElementById('email-modal').style.display = 'none';
  document.body.style.overflow = '';
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeEmail(); });

render();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Git push logic
# ---------------------------------------------------------------------------

def _run(cmd: list[str], cwd: Path, check: bool = True) -> str:
    result = subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, timeout=120
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command {cmd} failed (exit {result.returncode}):\n"
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def _ensure_clone() -> Path:
    clone = _CLONE_DIR
    if (clone / ".git").is_dir():
        _run(["git", "fetch", "origin"], cwd=clone)
        _run(["git", "reset", "--hard", "origin/main"], cwd=clone, check=False)
    else:
        clone.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", PUBLIC_REPO, str(clone)], cwd=clone.parent)
    return clone


def publish_snapshot() -> str:
    """Generate index.html and push to the public repo. Returns the public URL."""
    payload = _build_payload()
    json_blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    html = _HTML_TEMPLATE.replace("__GENERATED_AT__", payload["generated_at"])
    html = html.replace("__JSON_DATA__", json_blob)

    clone = _ensure_clone()
    out_path = clone / "index.html"
    out_path.write_text(html, encoding="utf-8")

    _run(["git", "config", "user.email", "publish@ainews-scout.local"], cwd=clone)
    _run(["git", "config", "user.name", "AINews Scout"], cwd=clone)
    _run(["git", "add", "index.html"], cwd=clone)

    # Only commit if there are actual changes.
    status = _run(["git", "status", "--porcelain"], cwd=clone)
    if status:
        _run(
            ["git", "commit", "-m", f"Snapshot {payload['generated_at']}"],
            cwd=clone,
        )
        _run(["git", "push", "origin", "main"], cwd=clone)

    return "https://zainab-abaid.github.io/ainews_public_view/"
