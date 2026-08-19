from __future__ import annotations

import re
from urllib.parse import urlparse

_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BRACKET_URL = re.compile(r"\[\s*(https?://[^\]]+?)\s*\]")
_HTTP = re.compile(r"https?://", re.I)
_QUOTED_LABEL = re.compile(
    r'([“"‘\'][^”"’\']{2,}[”"’\'](?:\s+\w+){0,4})\s*$'
)
_TOKEN = re.compile(
    r"\[([^\]]*)\]\((https?://[^)\s]+)\)|"
    r"\[\s*(https?://[^\]]+?)\s*\]|"
    r"https?://[^\s\]>)]+|"
    r"@?[^\W_]+(?:[.@_\-+’'][^\W_]+)*"
)


def short_link_label(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return "link"
    host = host.removeprefix("www.")
    return host or "link"


def normalize_inline_links(text: str) -> str:
    """Turn newsletter `[ https://... ]` URLs into Markdown links with short labels."""
    if not text:
        return text

    def keep_existing(m: re.Match[str]) -> str:
        label, url = m.group(1), m.group(2)
        if not label.strip() or _HTTP.match(label.strip()):
            return f"[{short_link_label(url)}]({url})"
        return m.group(0)

    text = _MD_LINK.sub(keep_existing, text)

    out: list[str] = []
    last = 0
    for m in _BRACKET_URL.finditer(text):
        prefix = text[last : m.start()]
        url = m.group(1).strip()
        quoted = _QUOTED_LABEL.search(prefix)
        if quoted:
            label = quoted.group(1).strip()
            prefix = prefix[: quoted.start()]
            out.append(prefix)
            out.append(f"[{label}]({url})")
        else:
            out.append(prefix)
            out.append(f"[{short_link_label(url)}]({url})")
        last = m.end()
    out.append(text[last:])
    return "".join(out)


def _tokens(text: str) -> list[tuple[str, str, int, int]]:
    items: list[tuple[str, str, int, int]] = []
    for m in _TOKEN.finditer(text):
        raw = m.group(0)
        kind = "link" if raw.startswith("[") or raw.startswith("http") else "word"
        value = raw.lower() if kind == "word" else raw
        items.append((kind, value, m.start(), m.end()))
    return items


def _body_words(tokens: list[tuple[str, str, int, int]]) -> list[tuple[str, int]]:
    words: list[tuple[str, int]] = []
    for i, (kind, value, _s, _e) in enumerate(tokens):
        if kind == "word":
            words.append((value, i))
            continue
        md = _MD_LINK.match(value)
        if md:
            for w in _excerpt_words(md.group(1)):
                words.append((w, i))
    return words


def _excerpt_words(excerpt: str) -> list[str]:
    return [value for kind, value, _s, _e in _tokens(excerpt) if kind == "word"]


def _body_span_for_excerpt(excerpt: str, body: str) -> str | None:
    tokens = _tokens(body)
    if not tokens:
        return None
    words = _body_words(tokens)
    ewords = _excerpt_words(excerpt)
    if len(ewords) < 6 or len(words) < 6:
        return None

    def find_seq(needle: list[str]) -> tuple[int, int] | None:
        n = len(needle)
        if n < 4:
            return None
        hay = [w for w, _i in words]
        limit = len(hay) - n + 1
        for start in range(max(limit, 0)):
            if hay[start : start + n] == needle:
                return start, start + n - 1
        return None

    found = find_seq(ewords)
    if found is None:
        head_n = min(12, len(ewords))
        tail_n = min(12, len(ewords))
        head = find_seq(ewords[:head_n])
        tail = find_seq(ewords[-tail_n:])
        if head is None or tail is None or tail[1] < head[0]:
            return None
        found = (head[0], tail[1])

    start_word, end_word = found
    start_tok = words[start_word][1]
    end_tok = words[end_word][1]
    while start_tok > 0 and tokens[start_tok - 1][0] == "link":
        start_tok -= 1
    while end_tok + 1 < len(tokens) and tokens[end_tok + 1][0] == "link":
        end_tok += 1
    start_ch = tokens[start_tok][2]
    end_ch = tokens[end_tok][3]
    return body[start_ch:end_ch].strip()


def hydrate_excerpt_links(excerpt: str, body: str) -> str:
    """Restore links the model dropped, using the matching passage in the email body."""
    excerpt = (excerpt or "").strip()
    if not excerpt:
        return excerpt
    span = _body_span_for_excerpt(excerpt, body or "")
    return normalize_inline_links(span or excerpt)
