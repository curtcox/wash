"""Minimal markdown→HTML helpers for the wash developer site.

Renders spec markdown with heading anchors and turns clause IDs (e.g.
``RT-10.5-multi-resource``) into links to the coverage page. Build-time only;
the served site is plain HTML/CSS with no client-side JavaScript.
"""

from __future__ import annotations

import html
import re

import markdown

# Clause ids look like RT-10.5-multi-resource or PP-4-implied-cat: an uppercase
# prefix, a dotted section number, then one or more kebab words.
CLAUSE_RE = re.compile(r"\b([A-Z]{2,}-\d+(?:\.\d+)*-[a-z0-9]+(?:-[a-z0-9]+)*)\b")

_HEADING_RE = re.compile(r"<(h[1-6])>(.*?)</\1>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def slugify(text: str) -> str:
    text = _TAG_RE.sub("", text)
    text = html.unescape(text).strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-") or "section"


def render_markdown(text: str) -> tuple[str, list[tuple[int, str, str]]]:
    """Return (html, toc) where toc is a list of (level, anchor, title)."""
    body = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )
    toc: list[tuple[int, str, str]] = []
    seen: dict[str, int] = {}

    def add_anchor(m: re.Match[str]) -> str:
        tag, inner = m.group(1), m.group(2)
        level = int(tag[1])
        title = _TAG_RE.sub("", inner).strip()
        # Numbered spec sections ("6.2 Command Shadowing") get the bare section
        # number as their id so the coverage page can link to "§6.2" directly.
        num = re.match(r"(\d+(?:\.\d+)*)\b", html.unescape(title))
        if num:
            anchor = "sec-" + num.group(1)
        else:
            base = slugify(inner)
            n = seen.get(base, 0)
            seen[base] = n + 1
            anchor = base if n == 0 else f"{base}-{n}"
        toc.append((level, anchor, html.unescape(title)))
        return f'<{tag} id="{anchor}">{inner}</{tag}>'

    body = _HEADING_RE.sub(add_anchor, body)
    body = _link_clauses(body)
    return body, toc


def _link_clauses(body: str) -> str:
    """Link clause ids to the coverage page, skipping ids already inside tags."""
    out: list[str] = []
    pos = 0
    # Walk tag-by-tag so we never rewrite inside attributes or code we already
    # emitted; only linkify text nodes outside of <code>/<pre> spans.
    for m in re.finditer(r"<pre>.*?</pre>|<code>.*?</code>|<[^>]+>", body, re.DOTALL):
        text = body[pos : m.start()]
        out.append(_clause_sub(text))
        out.append(m.group(0))
        pos = m.end()
    out.append(_clause_sub(body[pos:]))
    return "".join(out)


def _clause_sub(text: str) -> str:
    return CLAUSE_RE.sub(
        lambda m: (
            f'<a class="clause" href="coverage.html#{m.group(1)}">{m.group(1)}</a>'
        ),
        text,
    )


def render_toc(toc: list[tuple[int, str, str]], *, min_level: int = 2) -> str:
    items = [t for t in toc if t[0] >= min_level]
    if not items:
        return ""
    lines = ['<nav class="toc"><h2>On this page</h2><ul>']
    for level, anchor, title in items:
        lines.append(
            f'<li class="lvl{level}"><a href="#{anchor}">{html.escape(title)}</a></li>'
        )
    lines.append("</ul></nav>")
    return "\n".join(lines)
