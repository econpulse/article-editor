"""
Konvertiert Rich-Text-HTML-Fragmente aus dem Editor (z.B. <p>, <strong>, <em>, <ul>, <ol>, <li>)
sicher in valides Typst-Markup. Sonderzeichen wie #, $, @, *, _, <, >, [, ] werden zuverlässig
escaped, sodass Benutzereingaben niemals zu Typst-Kompilierungsfehlern führen.
"""

from __future__ import annotations

import functools
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

_EMPTY_P_OR_BR = r"(?:<p\b[^>]*>(?:\s|&nbsp;|<br\s*/?>)*</p>|<br\s*/?>|\s|&nbsp;)"
_LEADING_EMPTY_RE = re.compile(rf"^(?:{_EMPTY_P_OR_BR})+", re.IGNORECASE)
_TRAILING_EMPTY_RE = re.compile(rf"(?:{_EMPTY_P_OR_BR})+$", re.IGNORECASE)
_P_LEADING_BR = re.compile(r"(<p\b[^>]*>)(?:\s|&nbsp;|<br\s*/?>)+", re.IGNORECASE)
_P_TRAILING_BR = re.compile(r"(?:\s|&nbsp;|<br\s*/?>)+(</p>)", re.IGNORECASE)


@functools.lru_cache(maxsize=4096)
def sanitize_richtext_html(html_str: str) -> str:
    """
    Bereinigt und normalisiert RichText-HTML aus `contentEditable` und Browser-Copy-Paste:
    - Entfernt Kommentare sowie potenziell störende Tags (`<script>`, `<style>`, `<iframe>` etc.).
    - Konvertiert `<div>`-Container aus `document.execCommand` / Copy-Paste in saubere `<p>`-Absätze.
    - Bewahrt semantische Auszeichnungen (`<strong>`, `<b>`, `<em>`, `<i>`, `<u>`, `<sub>`, `<sup>`,
      `<ul>`, `<ol>`, `<li>`, `<br>`, `<a href="...">`, `<span class="glossary-term" data-tooltip="...">`,
      `<footnote>`).
    - Entfernt überflüssige leere Absätze und führende/nachgestellte `<br>`-Zeilenumbrüche, um
      Typst-Syntaxfehler durch verwaiste Zeilenumbrüche am Blockanfang/-ende zu verhindern.
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

    # Entferne führende und nachgestellte <br>-Tags innerhalb von Absätzen
    cleaned = _P_LEADING_BR.sub(r"\1", cleaned)
    cleaned = _P_TRAILING_BR.sub(r"\1", cleaned)

    # Entferne führende und nachgestellte leere Absätze und standalone <br>-Tags
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = _LEADING_EMPTY_RE.sub("", cleaned)
        cleaned = _TRAILING_EMPTY_RE.sub("", cleaned)

    return cleaned.strip()


@functools.lru_cache(maxsize=4096)
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


# Typografische Best-Practice-Schwelle (Option A):
# Absätze mit weniger als ca. 6 Zeilen (ca. 65 Wörter bzw. ~450 Zeichen) werden
# als unteilbare Blöcke (#block(breakable: false)[...]) gerendert, um Schusterjungen
# und Hurenkinder (Witwen) mit weniger als 3 Zeilen am Seiten- oder Spaltenwechsel
# vollständig zu unterbinden.
PARAGRAPH_KEEP_TOGETHER_MAX_WORDS: int = 65


class _HtmlToTypstParser(HTMLParser):
    def __init__(self, keep_together_max_words: int = PARAGRAPH_KEEP_TOGETHER_MAX_WORDS) -> None:
        super().__init__(convert_charrefs=True)
        self.keep_together_max_words: int = keep_together_max_words
        self.blocks: list[str] = []
        self.current_parts: list[str] = []
        self.current_word_count: int = 0
        self.list_parts: list[str] = []
        self.list_stack: list[str] = []  # "ul" oder "ol"
        self.in_li: bool = False
        # Stack offener Inline-Tags: (canonical_tag_name, closing_typst_markup)
        self.inline_stack: list[tuple[str, str]] = []

    def _append(self, markup: str) -> None:
        if self.list_stack:
            self.list_parts.append(markup)
        else:
            self.current_parts.append(markup)

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
                        self._append(close_str)
                return
        # Falls das schliessende Tag kein offenes Gegenstück hat (verwaistes End-Tag), ignorieren!

    def flush_open_inline_tags(self) -> None:
        """Schliesst alle noch offenen Inline-Klammern vor Blockende oder Textende."""
        while self.inline_stack:
            _tag, close_str = self.inline_stack.pop()
            if close_str:
                self._append(close_str)

    def _flush_current_paragraph(self) -> None:
        """Schliesst den aktuellen Textabsatz ab und formatiert ihn ggf. als unteilbaren Block."""
        self.flush_open_inline_tags()
        text_content = "".join(self.current_parts).strip()
        self.current_parts.clear()
        word_count = self.current_word_count
        self.current_word_count = 0

        # Bereinige führende und nachgestellte Typst-Zeilenumbrüche (\ bzw. \\\n) und Whitespace.
        # Ein nachgestellter Backslash vor dem Blockende "]" würde das schliessende "]" escapen
        # ("\]") und in Typst sofort zu einem fatalen "unclosed delimiter"-Kompilierungsfehler führen.
        # Ebenso wird ein Absatz, der ausschliesslich aus Zeilenumbrüchen oder Non-Breaking-Spaces
        # besteht, vollständig verworfen.
        text_content = re.sub(r"(\\+\s*)+$", "", text_content).strip()
        text_content = re.sub(r"^(\s*\\+)+", "", text_content).strip()

        stripped_check = text_content.replace("\\", "").replace("\xa0", "").strip()
        if not text_content or not stripped_check:
            return

        # Option A: Absätze unter der Schwelle als unteilbare Blöcke halten
        if 0 < self.keep_together_max_words and word_count <= self.keep_together_max_words:
            self.blocks.append(f"#block(breakable: false)[{text_content}]")
        else:
            self.blocks.append(text_content)

    def _flush_current_list(self) -> None:
        """Schliesst die aktuelle Liste ab und fügt sie zu den Blöcken hinzu."""
        self.flush_open_inline_tags()
        list_content = "".join(self.list_parts).strip()
        self.list_parts.clear()
        list_content = re.sub(r"(\\+\s*)+$", "", list_content).strip()
        stripped_check = list_content.replace("\\", "").replace("\xa0", "").strip()
        if list_content and stripped_check:
            self.blocks.append(list_content)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in ("p", "div"):
            if self.current_parts:
                self._flush_current_paragraph()
        elif t in ("ul", "ol"):
            if self.current_parts:
                self._flush_current_paragraph()
            self.flush_open_inline_tags()
            self.list_stack.append(t)
            self._append("\n")
        elif t == "li":
            self.flush_open_inline_tags()
            self.in_li = True
            indent = "  " * max(0, len(self.list_stack) - 1)
            marker = "+" if (self.list_stack and self.list_stack[-1] == "ol") else "-"
            self._append(f"{indent}{marker} ")
        elif t in ("b", "strong"):
            self._append("#strong[")
            self.inline_stack.append(("strong", "]"))
        elif t in ("i", "em"):
            self._append("#emph[")
            self.inline_stack.append(("emph", "]"))
        elif t == "u":
            self._append("#underline[")
            self.inline_stack.append(("u", "]"))
        elif t == "sub":
            self._append("#sub[")
            self.inline_stack.append(("sub", "]"))
        elif t == "sup":
            self._append("#sup[")
            self.inline_stack.append(("sup", "]"))
        elif t == "br":
            self._append(" \\\n")
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
                self._append(f'#link("{safe_url}")[#text(fill: rgb("#002855"))[')
                self.inline_stack.append(
                    ("a", '#h(0.18em)#box(baseline: -0.05em)[#text(size: 0.8em, fill: rgb("#005A9C"))[#sym.arrow.tr]]]]')
                )
            else:
                self._append("[")
                self.inline_stack.append(("a", "]"))
        elif t == "span":
            tooltip = ""
            for k, v in attrs:
                if k.lower() in ("data-tooltip", "title") and v:
                    tooltip = v.strip()
            if tooltip:
                self._append('#underline(stroke: 0.6pt + rgb("#009FE3"), offset: 1.5pt)[')
                self.inline_stack.append(("span", "]"))
            else:
                self.inline_stack.append(("span", ""))
        elif t == "footnote":
            self._append("#footnote[")
            self.inline_stack.append(("footnote", "]"))

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        canonical = self._canonical_inline_tag(t)
        if canonical is not None:
            self._close_inline_to(canonical)
        elif t in ("p", "div"):
            self._flush_current_paragraph()
        elif t == "li":
            self.flush_open_inline_tags()
            self.in_li = False
            self._append("\n")
        elif t in ("ul", "ol"):
            self.flush_open_inline_tags()
            if self.list_stack:
                self.list_stack.pop()
            self._append("\n")
            if not self.list_stack:
                self._flush_current_list()

    def handle_data(self, data: str) -> None:
        if not data:
            return
        # Normalisiere Zeilenumbrüche innerhalb von Absätzen
        cleaned = data.replace("\r\n", " ").replace("\n", " ")
        self._append(escape_typst_text(cleaned))
        if not self.list_stack:
            words = [w for w in cleaned.split() if w]
            self.current_word_count += len(words)

    def finalize(self) -> str:
        """Schliesst alle offenen Tags/Absätze ab und gibt den fertigen Typst-String zurück."""
        self.flush_open_inline_tags()
        if self.current_parts:
            self._flush_current_paragraph()
        if self.list_parts:
            self._flush_current_list()
        valid_blocks = [b.strip() for b in self.blocks if b and b.strip()]
        return "\n\n".join(valid_blocks).strip()


@functools.lru_cache(maxsize=4096)
def html_to_typst(
    html_str: str,
    keep_together_max_words: int = PARAGRAPH_KEEP_TOGETHER_MAX_WORDS,
) -> str:
    """Konvertiert einen HTML-String aus dem Rich-Text-Block in sicheren, klammerbalancierten Typst-Markup-Code."""
    if not html_str or not html_str.strip():
        return ""
    sanitized = sanitize_richtext_html(html_str)
    if not sanitized:
        return ""
    parser = _HtmlToTypstParser(keep_together_max_words=keep_together_max_words)
    try:
        parser.feed(sanitized)
        parser.close()
        result = parser.finalize()
    except Exception:
        plain = re.sub(r"<[^>]+>", " ", sanitized)
        plain = re.sub(r"(\\+\s*)+$", "", plain).strip()
        plain = re.sub(r"^(\s*\\+)+", "", plain).strip()
        escaped_plain = escape_typst_text(plain)
        escaped_plain = re.sub(r"(\\+\s*)+$", "", escaped_plain).strip()
        escaped_plain = re.sub(r"^(\s*\\+)+", "", escaped_plain).strip()
        if not escaped_plain or not escaped_plain.replace("\\", "").replace("\xa0", "").strip():
            return ""
        if 0 < keep_together_max_words and len(escaped_plain.split()) <= keep_together_max_words:
            return f"#block(breakable: false)[{escaped_plain}]"
        return escaped_plain
    return result


_TABLE_CELL_HTML_TAG_RE = re.compile(
    r"</?(?:b|strong|i|em|u|sub|sup|a|br|p|div|span)\b",
    re.IGNORECASE,
)


@functools.lru_cache(maxsize=4096)
def table_cell_html_to_typst(cell_val: str) -> str:
    """Konvertiert einen Tabellenzellen-Inhalt (Plaintext oder Inline-HTML) sicher in Typst-Markup."""
    if not cell_val:
        return ""
    raw = str(cell_val)
    if not raw.strip():
        return ""
    if not _TABLE_CELL_HTML_TAG_RE.search(raw):
        return escape_typst_text(raw).replace("\r\n", "\n").replace("\n", " \\\n")

    normalized = raw.replace("\r\n", "\n").replace("\n", "<br>")
    normalized = re.sub(r"</(?:p|div)>\s*<(?:p|div)\b[^>]*>", "<br>", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"</?(?:p|div)\b[^>]*>", "", normalized, flags=re.IGNORECASE)
    return html_to_typst(normalized, keep_together_max_words=0)
