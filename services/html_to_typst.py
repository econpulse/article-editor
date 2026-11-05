"""
Konvertiert Rich-Text-HTML-Fragmente aus dem Editor (z.B. <p>, <strong>, <em>, <ul>, <ol>, <li>)
sicher in valides Typst-Markup. Sonderzeichen wie #, $, @, *, _, <, >, [, ] werden zuverlässig
escaped, sodass Benutzereingaben niemals zu Typst-Kompilierungsfehlern führen.
"""

from __future__ import annotations

from html.parser import HTMLParser


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
        self.link_href_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in ("b", "strong"):
            self.parts.append("#strong[")
        elif t in ("i", "em"):
            self.parts.append("#emph[")
        elif t == "u":
            self.parts.append("#underline[")
        elif t == "sub":
            self.parts.append("#sub[")
        elif t == "sup":
            self.parts.append("#sup[")
        elif t == "br":
            self.parts.append(" \\\n")
        elif t in ("ul", "ol"):
            self.parts.append("\n")
            self.list_stack.append(t)
        elif t == "li":
            self.in_li = True
            indent = "  " * max(0, len(self.list_stack) - 1)
            marker = "+" if (self.list_stack and self.list_stack[-1] == "ol") else "-"
            self.parts.append(f"{indent}{marker} ")
        elif t == "a":
            href = ""
            for k, v in attrs:
                if k.lower() == "href" and v:
                    href = v.strip()
            self.link_href_stack.append(href)
            if href and (href.startswith("http://") or href.startswith("https://") or href.startswith("mailto:")):
                safe_url = href.replace("\\", "\\\\").replace('"', '\\"')
                self.parts.append(f'#link("{safe_url}")[')
            else:
                self.parts.append("[")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("b", "strong", "i", "em", "u", "sub", "sup"):
            self.parts.append("]")
        elif t == "a":
            if self.link_href_stack:
                self.link_href_stack.pop()
            self.parts.append("]")
        elif t == "p" or t == "div":
            self.parts.append("\n\n")
        elif t == "li":
            self.in_li = False
            self.parts.append("\n")
        elif t in ("ul", "ol"):
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
    """Konvertiert einen HTML-String aus dem Rich-Text-Block in sicheren Typst-Markup-Code."""
    if not html_str or not html_str.strip():
        return ""
    parser = _HtmlToTypstParser()
    parser.feed(html_str)
    parser.close()
    result = "".join(parser.parts).strip()
    return result
