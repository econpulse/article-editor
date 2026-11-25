// ============================================================================
// LUKB Factsheet (Fonds- & Strategieprofil) — 2-seitiges Template (Typst 0.15+)
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
  author: if meta.authors.len() > 0 { meta.authors.map(a => a.name) } else { ("LUKB Expert Fondsleitung AG",) }
)

#set text(
  font: font-body,
  weight: "light",
  size: 8.2pt,
  fill: lukb-text,
  lang: "de",
  region: "CH",
  costs: (orphan: 10000%, widow: 10000%)
)

#show strong: set text(font: font-heading, weight: "medium", fill: lukb-navy)

#set par(
  justify: true,
  leading: 0.54em,
  spacing: 1.0em
)

#let render-factsheet-footer(meta) = context {
  let page-num = counter(page).get().first()
  let total-pages = counter(page).final().first()
  let disclaimer = str(meta.at("disclaimer", default: "")).trim()

  align(top)[
    #block(
      width: 100%,
      inset: (top: 2.5pt),
      stroke: (top: 0.5pt + lukb-border)
    )[
      #grid(
        columns: (1fr, auto),
        column-gutter: 10pt,
        align: (left + bottom, right + bottom),
        [
          #set par(justify: false, leading: 0.22em)
          #cms-link-meta("meta-disclaimer")[
            #text(font: font-body, weight: "light", size: 5.6pt, fill: rgb("#555555"))[#disclaimer]
          ]
        ],
        [
          #text(font: font-heading, weight: "medium", size: 7.2pt, fill: lukb-muted)[#page-num/#total-pages]
        ]
      )
    ]
  ]
}

#set page(
  paper: "a4",
  margin: (top: 1.1cm, bottom: 1.5cm, left: 1.3cm, right: 1.3cm),
  footer-descent: 6pt,
  footer: render-factsheet-footer(meta)
)

#let render-factsheet-header(
  meta,
  title-text,
  title-size,
  title-color,
  subtitle-text,
  subtitle-color,
  kicker-text,
  kicker-color,
  border-color,
) = {
  v(-0.4cm)
  grid(
    columns: (1fr, auto),
    align: (left + horizon, right + horizon),
    [
      #image(resolve-asset-path("LUKB-Logo.svg"), height: 25pt)
    ],
    [
      #let has-series = meta.at("header_series", default: "") != ""
      #let pub-str = if has-series {
        meta.header_series
      } else {
        "Factsheet per " + format-pub-date(meta.publication_date)
      }
      #cms-link-meta(if has-series { "meta-header-series" } else { "meta-pub-date" })[
        // NOTIZ (vorherige Farbe): fill: lukb-muted (#5A687C)
        #text(font: font-heading, weight: "medium", size: 8.8pt, fill: lukb-blue-600)[#pub-str]
      ]
    ]
  )
  v(6pt)
  block(
    width: 100%,
    inset: (bottom: 5pt),
    stroke: (bottom: 1.5pt + border-color)
  )[
    #grid(
      columns: (1fr, auto),
      align: (left + bottom, right + bottom),
      [
        #cms-link-meta("meta-title")[
          #text(font: font-heading, weight: "medium", size: title-size, fill: title-color, tracking: -0.015em)[#title-text]
        ]
        #if subtitle-text != "" [
          #v(2pt)
          #cms-link-meta("meta-subtitle")[
            #text(font: font-body, weight: "light", size: 9pt, fill: subtitle-color)[#subtitle-text]
          ]
        ]
      ],
      [
        #if kicker-text != "" [
          #cms-link-meta("meta-category")[
            #text(font: font-heading, weight: "medium", size: 8.2pt, fill: kicker-color)[#kicker-text]
          ]
        ]
      ]
    )
  ]
  v(4pt)
}

#let render-factsheet-block(blk, callout-accent: lukb-cyan) = render-single-block(
  blk,
  in-box: true,
  is-margin: true,
  allow-float: true,
  table-style: "factsheet",
  callout-accent: callout-accent,
  heading-below: 0.30em,
)

#let render-factsheet-columns(left-blocks, right-blocks, left-accent, right-accent) = grid(
  columns: (1fr, 1fr),
  column-gutter: 14pt,
  align: (top + left, top + left),
  [ #for blk in left-blocks [ #render-factsheet-block(blk, callout-accent: left-accent) ] ],
  [ #for blk in right-blocks [ #render-factsheet-block(blk, callout-accent: right-accent) ] ],
)

// Partition blocks into sections by colbreak
#let sections = ( () , )
#for b in blocks {
  if b.type == "colbreak" {
    sections.push( () )
  } else {
    sections.last().push(b)
  }
}

#let p1-left = if sections.len() > 0 { sections.at(0) } else { () }
#let p1-right = if sections.len() > 1 { sections.at(1) } else { () }
#let p2-left = if sections.len() > 2 { sections.at(2) } else { () }
#let p2-right = if sections.len() > 3 { sections.at(3) } else { () }

// PAGE 1
// NOTIZ (vorherige Farben): title = lukb-navy, subtitle = lukb-blue, kicker = lukb-cyan
#render-factsheet-header(
  meta,
  meta.title,
  19pt,
  lukb-blue-600,
  meta.subtitle,
  lukb-blue-600,
  if meta.category != "" { upper(meta.category) } else { "" },
  lukb-blue-600,
  lukb-navy,
)
#render-factsheet-columns(p1-left, p1-right, lukb-cyan, lukb-navy)

#if sections.len() > 2 [
  #pagebreak()
  #render-factsheet-header(
    meta,
    "Aus Prinzip nachhaltig",
    17pt,
    rgb("#009FE3"),
    "Nachhaltigkeits- und ESG-Profil des Anlagefonds",
    lukb-muted,
    "ESG & STEWARDSHIP",
    lukb-navy,
    lukb-cyan,
  )
  #render-factsheet-columns(p2-left, p2-right, lukb-cyan, lukb-blue)
]
