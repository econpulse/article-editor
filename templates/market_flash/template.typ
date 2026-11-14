// ============================================================================
// LUKB Market Flash — Zweispaltiges Executive-Briefing-Layout (Typst 0.15+)
// Standard-Schriftart: Yoga Sans for LUKB Light
// Überschriften-Schriftart: Yoga Sans for LUKB Medium
// Nutzt das gemeinsame Basismodul `templates/_common/lukb_base.typ`.
// ============================================================================

#import "../_common/lukb_base.typ": *

#let payload = json(bytes(sys.inputs.at("article_json")))
#let meta = payload.metadata
#let blocks = payload.blocks

#set document(
  title: meta.title,
  author: if meta.authors.len() > 0 { meta.authors.map(a => a.name) } else { ("LUKB Investment Office",) }
)

#set text(
  font: font-body,
  weight: "light",
  size: 10pt,
  fill: lukb-text,
  lang: "de",
  region: "CH",
  costs: (orphan: 10000%, widow: 10000%)
)

#show strong: set text(font: font-heading, weight: "medium", fill: lukb-navy)

#set par(
  justify: true,
  leading: 0.72em,
  spacing: 2.0em
)

#set page(
  paper: "a4",
  margin: (top: page-top-margin, bottom: page-bottom-margin, left: page-side-margin, right: page-side-margin),
  footer-descent: 12pt,
  footer: render-page-footer(meta, page-font-size: 10pt)
)

// Seite 1 Dokumenten-Kopf (Dunkelblauer Executive-Briefing-Banner)
#render-executive-header(meta)

// Zweispaltiger Hauptteil mit goldenen Callout-Akzenten & O(N)-Spaltenausgleich
#render-two-column-body(
  blocks,
  gutter: 16pt,
  callout-accent: lukb-gold,
  quote-accent: lukb-cyan,
  heading-below: 0.72em,
)
