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
          #text(font: font-body, weight: "light", size: 5.6pt, fill: rgb("#555555"))[#disclaimer]
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

#let render-factsheet-header-page1(meta) = {
  v(-0.4cm)
  grid(
    columns: (1fr, auto),
    align: (left + horizon, right + horizon),
    [
      #image(resolve-asset-path("LUKB-Logo.svg"), height: 25pt)
    ],
    [
      #let pub-str = if meta.at("header_series", default: "") != "" {
        meta.header_series
      } else {
        "Factsheet per " + format-pub-date(meta.publication_date)
      }
      #text(font: font-heading, weight: "medium", size: 8.8pt, fill: lukb-muted)[#pub-str]
    ]
  )
  v(6pt)
  block(
    width: 100%,
    inset: (bottom: 5pt),
    stroke: (bottom: 1.5pt + lukb-navy)
  )[
    #grid(
      columns: (1fr, auto),
      align: (left + bottom, right + bottom),
      [
        #text(font: font-heading, weight: "medium", size: 19pt, fill: lukb-navy)[#meta.title]
        #if meta.subtitle != "" [
          #v(2pt)
          #text(font: font-body, weight: "light", size: 9pt, fill: lukb-blue)[#meta.subtitle]
        ]
      ],
      [
        #if meta.category != "" [
          #text(font: font-heading, weight: "medium", size: 8.2pt, fill: lukb-cyan)[#upper(meta.category)]
        ]
      ]
    )
  ]
  v(4pt)
}

#let render-factsheet-header-page2(meta) = {
  v(-0.4cm)
  grid(
    columns: (1fr, auto),
    align: (left + horizon, right + horizon),
    [
      #image(resolve-asset-path("LUKB-Logo.svg"), height: 25pt)
    ],
    [
      #let pub-str = if meta.at("header_series", default: "") != "" {
        meta.header_series
      } else {
        "Factsheet per " + format-pub-date(meta.publication_date)
      }
      #text(font: font-heading, weight: "medium", size: 8.8pt, fill: lukb-muted)[#pub-str]
    ]
  )
  v(6pt)
  block(
    width: 100%,
    inset: (bottom: 5pt),
    stroke: (bottom: 1.5pt + lukb-cyan)
  )[
    #grid(
      columns: (1fr, auto),
      align: (left + bottom, right + bottom),
      [
        #text(font: font-heading, weight: "medium", size: 17pt, fill: rgb("#009FE3"))[Aus Prinzip nachhaltig]
        #v(2pt)
        #text(font: font-body, weight: "light", size: 9pt, fill: lukb-muted)[Nachhaltigkeits- und ESG-Profil des Anlagefonds]
      ],
      [
        #text(font: font-heading, weight: "medium", size: 8.2pt, fill: lukb-navy)[ESG & STEWARDSHIP]
      ]
    )
  ]
  v(4pt)
}

#let render-factsheet-block(blk, callout-accent: lukb-cyan) = {
  if blk.type == "table" {
    let bcopy = blk
    bcopy.insert("layout", "column")
    render-table-box(bcopy, is-margin: true, style-variant: "factsheet")
  } else if blk.type in ("figure", "db_chart", "custom_chart") {
    let bcopy = blk
    bcopy.insert("layout", "column")
    render-figure-box(bcopy, is-margin: true)
  } else if blk.type == "heading" {
    render-heading(blk.level, blk.text, below-space: 0.30em)
  } else if blk.type == "richtext" {
    eval(blk.typst_markup, mode: "markup")
    parbreak()
  } else if blk.type == "callout" {
    render-callout(blk.title, blk.typst_markup, accent-color: callout-accent)
  } else {
    render-single-block(blk, callout-accent: callout-accent, heading-below: 0.30em)
  }
}

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
#render-factsheet-header-page1(meta)
#grid(
  columns: (1fr, 1fr),
  column-gutter: 14pt,
  align: (top + left, top + left),
  [ #for blk in p1-left [ #render-factsheet-block(blk, callout-accent: lukb-cyan) ] ],
  [ #for blk in p1-right [ #render-factsheet-block(blk, callout-accent: lukb-navy) ] ]
)

#if sections.len() > 2 [
  #pagebreak()
  #render-factsheet-header-page2(meta)
  #grid(
    columns: (1fr, 1fr),
    column-gutter: 14pt,
    align: (top + left, top + left),
    [ #for blk in p2-left [ #render-factsheet-block(blk, callout-accent: lukb-cyan) ] ],
    [ #for blk in p2-right [ #render-factsheet-block(blk, callout-accent: lukb-blue) ] ]
  )
]
