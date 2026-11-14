"""
Konvertiert Rich-Text-HTML-Fragmente aus dem Editor (z.B. <p>, <strong>, <em>, <ul>, <ol>, <li>)
sicher in valides Typst-Markup. Sonderzeichen wie #, $, @, *, _, <, >, [, ] werden zuverlässig
escaped, sodass Benutzereingaben niemals zu Typst-Kompilierungsfehlern führen.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser


_DANGEROUS_BLOCKS_RE = re.compile(
    r"<(script|style|iframe|object|embed|meta|link)\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_DANGEROUS_SELF_RE = re.compile(
    r"<(script|style|iframe|object|embed|meta|link)\b[^>]*/?>",
    re.IGNORECASE,
)
_HTML_COMMENTS_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def sanitize_richtext_html(html_str: str) -> str:
    """
    Bereinigt und normalisiert RichText-HTML aus `contentEditable` und Browser-Copy-Paste:
    - Entfernt Kommentare sowie potenziell störende Tags (`<script>`, `<style>`, `<iframe>` etc.).
    - Konvertiert `<div>`-Container aus `document.execCommand` / Copy-Paste in saubere `<p>`-Absätze.
    - Bewahrt semantische Auszeichnungen (`<strong>`, `<b>`, `<em>`, `<i>`, `<u>`, `<sub>`, `<sup>`,
      `<ul>`, `<ol>`, `<li>`, `<br>`, `<a href="...">`, `<span class="glossary-term" data-tooltip="...">`,
      `<footnote>`).
    """
    if not html_str or not html_str.strip():
        return ""
    cleaned = _HTML_COMMENTS_RE.sub("", html_str)
    cleaned = _DANGEROUS_BLOCKS_RE.sub("", cleaned)
    cleaned = _DANGEROUS_SELF_RE.sub("", cleaned)
    # Konvertiere <div>...</div> aus contentEditable-Zeilenumbrüchen in <p>...</p>
    cleaned = re.sub(r"<div\b[^>]*>", "<p>", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</div\s*>", "</p>", cleaned, flags=re.IGNORECASE)
    # Entferne leere verschachtelte <p><p>-Dopplungen
    cleaned = re.sub(r"<p>\s*<p>", "<p>", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</p>\s*</p>", "</p>", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def escape_typst_text(text: str) -> str:
    """Escaped alle in Typst-Markup reservierten Zeichen in reinem Text."""
    if not text:
        return ""
    replacements = [
        ("\\", "\\\\"),
        ("#", "\\#"),
        ("$", "\\$"),
        ("@", "\\@"),
        ("*", "\\*"),
        ("_", "\\_"),
        ("`", "\\`"),
        ("<", "\\<"),
        (">", "\\>"),
        ("[", "\\["),
        ("]", "\\]"),
        ("~", "\\~"),
    ]
    out = text
    for src, target in replacements:
        out = out.replace(src, target)
    return out


class _HtmlToTypstParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.list_stack: list[str] = []  # "ul" oder "ol"
        self.in_li: bool = False
        # Stack offener Inline-Tags: (canonical_tag_name, closing_typst_markup)
        self.inline_stack: list[tuple[str, str]] = []

    @staticmethod
    def _canonical_inline_tag(tag: str) -> str | None:
        t = tag.lower()
        if t in ("b", "strong"):
            return "strong"
        if t in ("i", "em"):
            return "emph"
        if t in ("u", "sub", "sup", "a", "span", "footnote"):
            return t
        return None

    def _close_inline_to(self, canonical_tag: str) -> None:
        """Schliesst das angegebene Inline-Tag (sowie etwaige ungeschlossene innere Inline-Tags) klammerbalanciert."""
        for idx in range(len(self.inline_stack) - 1, -1, -1):
            if self.inline_stack[idx][0] == canonical_tag:
                # Schliesse alle inneren Tags bis einschliesslich idx in umgekehrter Reihenfolge
                while len(self.inline_stack) > idx:
                    _tag, close_str = self.inline_stack.pop()
                    if close_str:
                        self.parts.append(close_str)
                return
        # Falls das schliessende Tag kein offenes Gegenstück hat (verwaistes End-Tag), ignorieren!

    def flush_open_inline_tags(self) -> None:
        """Schliesst alle noch offenen Inline-Klammern vor Blockende oder Textende."""
        while self.inline_stack:
            _tag, close_str = self.inline_stack.pop()
            if close_str:
                self.parts.append(close_str)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in ("b", "strong"):
            self.parts.append("#strong[")
            self.inline_stack.append(("strong", "]"))
        elif t in ("i", "em"):
            self.parts.append("#emph[")
            self.inline_stack.append(("emph", "]"))
        elif t == "u":
            self.parts.append("#underline[")
            self.inline_stack.append(("u", "]"))
        elif t == "sub":
            self.parts.append("#sub[")
            self.inline_stack.append(("sub", "]"))
        elif t == "sup":
            self.parts.append("#sup[")
            self.inline_stack.append(("sup", "]"))
        elif t == "br":
            self.parts.append(" \\\n")
        elif t in ("ul", "ol"):
            self.flush_open_inline_tags()
            self.parts.append("\n")
            self.list_stack.append(t)
        elif t == "li":
            self.flush_open_inline_tags()
            self.in_li = True
            indent = "  " * max(0, len(self.list_stack) - 1)
            marker = "+" if (self.list_stack and self.list_stack[-1] == "ol") else "-"
            self.parts.append(f"{indent}{marker} ")
        elif t == "a":
            href = ""
            for k, v in attrs:
                if k.lower() == "href" and v:
                    href = v.strip()
            is_valid_link = bool(
                href and (href.startswith("http://") or href.startswith("https://") or href.startswith("mailto:"))
            )
            if is_valid_link:
                safe_url = href.replace("\\", "\\\\").replace('"', '\\"')
                self.parts.append(f'#link("{safe_url}")[#text(fill: rgb("#002855"))[')
                self.inline_stack.append(
                    ("a", '#h(0.18em)#box(baseline: -0.05em)[#text(size: 0.8em, fill: rgb("#005A9C"))[#sym.arrow.tr]]]]')
                )
            else:
                self.parts.append("[")
                self.inline_stack.append(("a", "]"))
        elif t == "span":
            tooltip = ""
            for k, v in attrs:
                if k.lower() in ("data-tooltip", "title") and v:
                    tooltip = v.strip()
            if tooltip:
                self.parts.append('#underline(stroke: 0.6pt + rgb("#009FE3"), offset: 1.5pt)[')
                self.inline_stack.append(("span", "]"))
            else:
                self.inline_stack.append(("span", ""))
        elif t == "footnote":
            self.parts.append("#footnote[")
            self.inline_stack.append(("footnote", "]"))

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        canonical = self._canonical_inline_tag(t)
        if canonical is not None:
            self._close_inline_to(canonical)
        elif t in ("p", "div"):
            self.flush_open_inline_tags()
            self.parts.append("\n\n")
        elif t == "li":
            self.flush_open_inline_tags()
            self.in_li = False
            self.parts.append("\n")
        elif t in ("ul", "ol"):
            self.flush_open_inline_tags()
            if self.list_stack:
                self.list_stack.pop()
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not data:
            return
        # Normalisiere Zeilenumbrüche innerhalb von Absätzen
        cleaned = data.replace("\r\n", " ").replace("\n", " ")
        self.parts.append(escape_typst_text(cleaned))


def html_to_typst(html_str: str) -> str:
    """Konvertiert einen HTML-String aus dem Rich-Text-Block in sicheren, klammerbalancierten Typst-Markup-Code."""
    if not html_str or not html_str.strip():
        return ""
    sanitized = sanitize_richtext_html(html_str)
    if not sanitized:
        return ""
    parser = _HtmlToTypstParser()
    try:
        parser.feed(sanitized)
        parser.close()
        parser.flush_open_inline_tags()
    except Exception:
        plain = re.sub(r"<[^>]+>", " ", sanitized)
        return escape_typst_text(plain.strip())
    result = "".join(parser.parts).strip()
    return result
