// ============================================================================
// LUKB Investment Fokus (Tufte-Stil) — Publikations-Template (Typst 0.15+)
// Standard-Schriftart: Yoga Sans for LUKB Light
// Überschriften-Schriftart: Yoga Sans for LUKB Medium
// Asymmetrischer Body-Satz: 116mm Hauptspalte + 8mm Steg + 56mm Randbereich
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
  size: 9.5pt,
  fill: lukb-text,
  lang: "de",
  region: "CH",
  costs: (orphan: 10000%, widow: 10000%)
)

#show strong: set text(font: font-heading, weight: "medium", fill: lukb-navy)

#set par(
  justify: true,
  leading: 0.68em,
  spacing: 1.8em
)

#set page(
  paper: "a4",
  margin: (top: page-top-margin, bottom: page-bottom-margin, left: page-side-margin, right: page-side-margin),
  footer-descent: 12pt,
  footer: render-page-footer(meta, page-font-size: 9.5pt)
)

// Seite 1 Dokumenten-Kopf (Standard LUKB Investment Fokus)
#render-standard-header(meta, title-below: 2.2em, lead-below: 2.2em)

// Asymmetrischer Tufte-Hauptteil mit entkoppelter Randspalten-Höhenlogik
#render-tufte-body(blocks)
