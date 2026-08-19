from __future__ import annotations

import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any, Optional

from backend.services.links import normalize_inline_links, short_link_label


def decode_b64(data: str) -> bytes:
    import base64

    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def html_to_markdown(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", "", html)
    html = re.sub(r"(?is)<!--.*?-->", "", html)

    def repl_a(match: re.Match[str]) -> str:
        attrs, inner = match.group(1), match.group(2)
        href_m = re.search(r'(?i)href\s*=\s*["\']([^"\']+)["\']', attrs)
        href = unescape(href_m.group(1)).strip() if href_m else ""
        text = unescape(re.sub(r"<[^>]+>", "", inner))
        text = re.sub(r"\s+", " ", text).strip()
        if not href or href.lower().startswith(("javascript:", "data:")):
            return text
        if href.startswith("#"):
            return text
        if not text or text == href or text.lower().startswith("http"):
            return f"[{short_link_label(href)}]({href})"
        return f"[{text}]({href})"

    html = re.sub(r"(?is)<a\s+([^>]*?)>(.*?)</a>", repl_a, html)
    html = re.sub(r"(?i)<h1[^>]*>", "\n\n# ", html)
    html = re.sub(r"(?i)</h1>", "\n\n", html)
    html = re.sub(r"(?i)<h2[^>]*>", "\n\n## ", html)
    html = re.sub(r"(?i)</h2>", "\n\n", html)
    html = re.sub(r"(?i)<h[3-6][^>]*>", "\n\n### ", html)
    html = re.sub(r"(?i)</h[3-6]>", "\n\n", html)
    html = re.sub(r"(?i)<(strong|b)(\s[^>]*)?>", "**", html)
    html = re.sub(r"(?i)</(strong|b)>", "**", html)
    html = re.sub(r"(?i)<(em|i)(\s[^>]*)?>", "*", html)
    html = re.sub(r"(?i)</(em|i)>", "*", html)
    html = re.sub(r"(?i)<li[^>]*>", "\n- ", html)
    html = re.sub(r"(?i)</li>", "\n", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</p>", "\n\n", html)
    html = re.sub(r"(?i)</div>", "\n", html)
    html = re.sub(r"(?i)</tr>", "\n", html)
    html = re.sub(r"(?i)</h[1-6]>", "\n\n", html)
    html = re.sub(r"(?i)<hr[^>]*>", "\n\n---\n\n", html)
    html = re.sub(r"<[^>]+>", "", html)
    text = unescape(html).replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return normalize_inline_links(text.strip())


def parse_date(s: str) -> Optional[datetime]:
    s = (s or "").strip()
    if not s:
        return None
    m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d")
        except ValueError:
            pass
    try:
        dt = parsedate_to_datetime(s)
        return dt.replace(tzinfo=None)
    except (TypeError, ValueError, OverflowError):
        pass
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})", s)
    if m:
        for fmt in ("%d %b %Y", "%d %B %Y"):
            try:
                return datetime.strptime(
                    f"{m.group(1)} {m.group(2)} {m.group(3)}", fmt
                )
            except ValueError:
                continue
    return None


def _decode_data(raw: Optional[str]) -> str:
    if not raw:
        return ""
    try:
        return decode_b64(raw).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _collect_payload(payload: dict[str, Any]) -> tuple[str, str]:
    mime = (payload.get("mimeType") or "").lower()
    body = payload.get("body") or {}
    data = body.get("data")
    parts = payload.get("parts") or []

    plain = ""
    html = ""
    if mime == "text/plain" and data:
        plain = _decode_data(data)
    elif mime == "text/html" and data:
        html = _decode_data(data)
    elif data and not parts:
        raw = _decode_data(data)
        if "html" in mime:
            html = raw
        else:
            plain = raw

    for part in parts:
        p, h = _collect_payload(part)
        if p and not plain:
            plain = p
        if h and not html:
            html = h
    return plain, html


def gmail_payload_text(payload: dict[str, Any]) -> str:
    plain, html = _collect_payload(payload)
    if html:
        md = html_to_markdown(html)
        if md:
            return md
    if plain:
        return normalize_inline_links(plain.strip())
    return ""


def headers_map(payload: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in payload.get("headers") or []:
        name = (item.get("name") or "").strip()
        if name:
            out[name.lower()] = item.get("value") or ""
    return out


def format_email_markdown(
    subject: str,
    from_addr: str,
    date_raw: str,
    body: str,
    source: str,
    message_id: str = "",
    to_addr: str = "",
) -> str:
    lines = [f"# {subject or '(no subject)'}", "", f"- **From:** {from_addr or '(unknown)'}"]
    if to_addr:
        lines.append(f"- **To:** {to_addr}")
    lines.extend(
        [
            f"- **Date:** {date_raw or '(unknown)'}",
            f"- **Source:** {source}",
        ]
    )
    if message_id:
        lines.append(f"- **Message-ID:** {message_id}")
    lines.extend(["", "---", "", body.strip(), ""])
    return "\n".join(lines)


def gmail_message_markdown(payload: dict[str, Any], source: str) -> str:
    """The stored form of a Gmail message. Sync and re-import share this, so a
    re-imported body is identical to a freshly fetched one."""
    headers = headers_map(payload)
    return format_email_markdown(
        headers.get("subject") or "(no subject)",
        headers.get("from") or "",
        headers.get("date") or "",
        gmail_payload_text(payload),
        source,
        (headers.get("message-id") or "").strip(),
        headers.get("to") or "",
    )
