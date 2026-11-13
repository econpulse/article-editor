// ============================================================================
// LUKB Investment Fokus (Tufte-Stil) — Publikations-Template (Typst 0.15+)
// Standard-Schriftart: Yoga Sans for LUKB Light
// Überschriften-Schriftart: Yoga Sans for LUKB Medium
// Asymmetrischer Body-Satz: 116mm Hauptspalte + 8mm Steg + 56mm Randbereich
// Einspaltige Grafiken & Tabellen im Randbereich, zweispaltige über gesamte Breite.
// ============================================================================

#let payload = json(bytes(sys.inputs.at("article_json")))
#let meta = payload.metadata
#let blocks = payload.blocks

#let format-pub-date(d) = {
  if d == none or d == "" { return "" }
  let s = str(d).trim()
  let months = ("", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember")
  let parts = s.split("-")
  if parts.len() == 3 {
    let y = parts.at(0)
    let m = int(parts.at(1))
    let d-part = parts.at(2).slice(0, calc.min(2, parts.at(2).len()))
    let day = int(d-part)
    if m >= 1 and m <= 12 {
      return str(day) + ". " + months.at(m) + " " + y
    }
  }
  return s
}

// LUKB Corporate Design Farbpalette
#let lukb-navy = rgb("#002855")
#let lukb-blue = rgb("#005A9C")
#let lukb-cyan = rgb("#009FE3")
#let lukb-gold = rgb("#C59B27")
#let lukb-text = rgb("#1A2433")
#let lukb-muted = rgb("#5A687C")
#let lukb-surface = rgb("#F4F7FA")
#let lukb-border = rgb("#D6DEE8")

// Schriftfamilien gemäss LUKB Corporate Design Vorgabe
#let font-body = ("Yoga Sans for LUKB Light", "Yoga Sans for LUKB", "Calibri Light", "Calibri", "Arial")
#let font-heading = ("Yoga Sans for LUKB Medium", "Yoga Sans for LUKB", "Calibri", "Arial")

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

// Stark hervorgehobener Text im Fliesstext nutzt automatisch Yoga Sans for LUKB Medium
#show strong: set text(font: font-heading, weight: "medium", fill: lukb-navy)

#set par(
  justify: true,
  leading: 0.68em,
  spacing: 1.8em
)

#set page(
  paper: "a4",
  margin: (top: 2cm, bottom: 2.4cm, left: 1.5cm, right: 1.5cm),
  footer-descent: 12pt,
  footer: context {
    let page-num = counter(page).get().first()
    let total-pages = counter(page).final().first()
    let page-str = text(font: font-body, weight: "light", size: 9.5pt, fill: lukb-muted)[#page-num/#total-pages]

    if page-num == 1 and meta.disclaimer != "" {
      align(top)[
        #block(
          width: 100%,
          inset: (top: 5pt),
          stroke: (top: 0.5pt + black)
        )[
          #set par(justify: false, leading: 0.25em)
          #text(font: font-body, weight: "light", size: 6.8pt, fill: black)[#meta.disclaimer]
          #v(2pt)
          #align(right)[
            #move(dy: -0.5cm)[#page-str]
          ]
        ]
      ]
    } else {
      align(top)[
        #block(
          width: 100%,
          inset: (top: 5pt),
          stroke: (top: 0.5pt + lukb-border)
        )[
          #v(2pt)
          #align(right)[
            #page-str
          ]
        ]
      ]
    }
  }
)

// ============================================================================
// Komponenten-Bausteine
// ============================================================================

#let render-heading(level, content-text) = {
  let sz = if level == 1 { 13.5pt } else if level == 2 { 10.5pt } else { 9.6pt }
  let col = if level == 1 { lukb-navy } else if level == 2 { lukb-blue } else { lukb-text }
  let lead = if level == 1 { 0.40em } else if level == 2 { 0.36em } else { 0.32em }
  let abv = 1.8em
  let blw = if level == 1 { 6pt } else { 0.65em }
  if level == 1 {
    block(
      width: 100%,
      sticky: true,
      breakable: false,
      above: abv,
      below: blw
    )[
      #stack(
        spacing: 4pt,
        block(width: 100%)[
          #set text(hyphenate: false)
          #set par(leading: lead, justify: false)
          #text(font: font-heading, weight: "medium", size: sz, fill: col)[#content-text]
        ],
        line(length: 100%, stroke: 0.75pt + lukb-navy)
      )
    ]
  } else {
    block(
      width: 100%,
      sticky: true,
      breakable: false,
      above: abv,
      below: blw
    )[
      #set text(hyphenate: false)
      #set par(leading: lead, justify: false)
      #text(font: font-heading, weight: "medium", size: sz, fill: col)[#content-text]
    ]
  }
}

#let render-callout(title, markup-str) = {
  block(
    width: 100%,
    breakable: false,
    fill: lukb-surface,
    stroke: (left: 3pt + lukb-cyan, top: 0.5pt + lukb-border, right: 0.5pt + lukb-border, bottom: 0.5pt + lukb-border),
    inset: (x: 10pt, y: 9pt),
    radius: (right: 3pt),
    above: 1.0em,
    below: 1.1em
  )[
    #if title != "" [
      #block(above: 0pt, below: 0.8em)[
        #text(font: font-heading, weight: "medium", size: 9.5pt, fill: lukb-navy)[#title]
      ]
    ]
    #set text(size: 8.8pt)
    #set par(spacing: 0.9em)
    #set list(spacing: 0.65em)
    #eval(markup-str, mode: "markup")
  ]
}

#let render-figure-box(blk, is-margin: false) = {
  let title-sz = if is-margin { 8.8pt } else { 10pt }
  let sub-sz = if is-margin { 7.6pt } else { 8.3pt }
  let src-sz = if is-margin { 6.8pt } else { 7.5pt }

  block(
    width: 100%,
    breakable: false,
    stroke: (top: 1.5pt + lukb-navy, bottom: 0.6pt + lukb-border),
    inset: (top: 6pt, bottom: 5pt),
    above: if is-margin { 0.4em } else { 1.5em },
    below: if is-margin { 0.6em } else { 1.2em }
  )[
    #if blk.title != "" [
      #block(above: 0pt, below: if blk.subtitle != "" { 4.5pt } else { 5pt })[
        #set par(leading: 0.28em, justify: false)
        #text(font: font-heading, weight: "medium", size: title-sz, fill: lukb-navy)[#blk.title]
      ]
    ]
    #if blk.subtitle != "" [
      #block(above: 0pt, below: 5pt)[
        #set par(leading: 0.28em, justify: false)
        #text(font: font-body, weight: "light", size: sub-sz, fill: lukb-muted)[#blk.subtitle]
      ]
    ]
    #if blk.at("resolved_image", default: "") != "" [
      #align(center)[
        #image(blk.resolved_image, width: 100%)
      ]
    ] else [
      #rect(
        width: 100%,
        height: if is-margin { 75pt } else { 95pt },
        fill: lukb-surface,
        stroke: (paint: lukb-border, dash: "dashed")
      )[
        #align(center + horizon)[
          #text(size: 7.5pt, fill: lukb-muted)[Grafik-Platzhalter (Bitte SVG oder PNG im Editor hochladen)]
        ]
      ]
    ]
    #if blk.source != "" [
      #v(2pt)
      #text(font: font-body, weight: "light", size: src-sz, fill: lukb-muted)[#blk.source]
    ]
  ]
}

#let render-table-box(blk, is-margin: false) = {
  let cols = blk.columns
  let rows = blk.rows
  let col-count = if cols.len() > 0 { cols.len() } else { 1 }

  let aligns = cols.map(c => {
    if c.align == "right" { right + top }
    else if c.align == "center" { center + top }
    else { left + top }
  })

  let fallback-w = if cols.len() > 0 { 100.0 / cols.len() } else { 100.0 }
  let col-widths = cols.map(c => {
    let raw-w = float(c.at("width", default: fallback-w))
    let safe-w = if raw-w > 0 { raw-w } else { fallback-w }
    safe-w * 1fr
  })

  let cell-sz = if is-margin { 7.4pt } else { 8.3pt }
  let hdr-sz = if is-margin { 7.4pt } else { 8.3pt }
  let title-sz = if is-margin { 8.8pt } else { 10pt }
  let sub-sz = if is-margin { 7.6pt } else { 8.3pt }
  let pad-x = if is-margin { 3.5pt } else { 5.5pt }
  let pad-y = if is-margin { 3pt } else { 4pt }

  block(
    width: 100%,
    breakable: not is-margin,
    above: if is-margin { 0.4em } else { 1.2em },
    below: if is-margin { 0.6em } else { 1.2em }
  )[
    #block(
      width: 100%,
      sticky: true,
      breakable: false,
      stroke: (top: 1.5pt + lukb-navy),
      inset: (top: 6pt),
      above: 0pt,
      below: if blk.title != "" or blk.subtitle != "" { 5pt } else { 2pt }
    )[
      #if blk.title != "" [
        #block(above: 0pt, below: if blk.subtitle != "" { 4pt } else { 0pt })[
          #set par(leading: 0.28em, justify: false)
          #text(font: font-heading, weight: "medium", size: title-sz, fill: lukb-navy)[#blk.title]
        ]
      ]
      #if blk.subtitle != "" [
        #block(above: 0pt, below: 0pt)[
          #set par(leading: 0.28em, justify: false)
          #text(font: font-body, weight: "light", size: sub-sz, fill: lukb-muted)[#blk.subtitle]
        ]
      ]
    ]

    #set table.cell(breakable: false)
    #let show-header = blk.at("show_header", default: true)
    #table(
      columns: col-widths,
      align: aligns,
      stroke: (x, y) => (
        top: if show-header {
          if y == 0 { 0.8pt + lukb-navy } else if y == 1 { 0.8pt + lukb-navy } else { 0.4pt + lukb-border }
        } else {
          if y == 0 { 0.8pt + lukb-navy } else { 0.4pt + lukb-border }
        },
        bottom: if y == rows.len() + (if show-header { 0 } else { -1 }) { 0.8pt + lukb-navy } else { none },
        left: none,
        right: none
      ),
      fill: (col, row) => {
        if show-header and row == 0 {
          lukb-surface
        } else if blk.at("highlight_last_row", default: false) and row == rows.len() + (if show-header { 0 } else { -1 }) {
          rgb("#EDF3FA")
        } else if calc.even(row) {
          rgb("#FAFBFD")
        } else {
          none
        }
      },
      inset: (x: pad-x, y: pad-y),

      // Header Zeile
      ..if show-header {
        cols.map(c => [
          #set text(font: font-heading, weight: "medium", size: hdr-sz, fill: lukb-navy)
          #set par(leading: 0.25em, justify: false)
          #c.title
        ])
      } else { () },

      // Daten-Zeilen
      ..rows.enumerate().map(((r-idx, r)) => {
        let is-total-row = blk.at("highlight_last_row", default: false) and (r-idx == rows.len() - 1)
        cols.map(c => [
          #set text(
            font: if is-total-row { font-heading } else { font-body },
            weight: if is-total-row { "medium" } else { "light" },
            size: cell-sz,
            fill: if is-total-row { lukb-navy } else { lukb-text }
          )
          #set par(leading: 0.25em, justify: false)
          #r.at(c.field, default: "")
        ])
      }).flatten()
    )

    #if blk.source != "" [
      #v(3pt)
      #text(font: font-body, weight: "light", size: if is-margin { 6.8pt } else { 7.5pt }, fill: lukb-muted)[#blk.source]
    ]
  ]
}

#let render-quote-box(quote-text, author, source, is-margin: false) = {
  let q-sz = if is-margin { 8.8pt } else { 10.2pt }
  block(
    width: 100%,
    breakable: false,
    stroke: (left: 3pt + lukb-gold),
    inset: (left: 9pt, top: 4pt, bottom: 4pt),
    above: 1.0em,
    below: 1.1em
  )[
    #set par(leading: 0.45em, justify: false)
    #text(font: font-heading, weight: "medium", size: q-sz, fill: lukb-navy)[«#quote-text»]
    #if author != "" or source != "" [
      #v(3pt)
      #text(font: font-body, weight: "light", size: 7.8pt, fill: lukb-muted)[
        #if author != "" [ *#author* ]
        #if author != "" and source != "" [ · ]
        #if source != "" [ #source ]
      ]
    ]
  ]
}

#let render-divider(style) = {
  let p = if style == "dashed" {
    line(length: 100%, stroke: (paint: lukb-border, dash: "dashed", thickness: 0.75pt))
  } else if style == "double" {
    stack(
      spacing: 2pt,
      line(length: 100%, stroke: 0.6pt + lukb-navy),
      line(length: 100%, stroke: 0.6pt + lukb-navy)
    )
  } else {
    line(length: 100%, stroke: 0.75pt + lukb-border)
  }
  block(width: 100%, above: 1.4em, below: 1.4em)[#p]
}

#let render-footnotes-box(title, items) = {
  if items.len() == 0 { return }
  block(
    width: 100%,
    stroke: (top: 0.8pt + lukb-navy),
    inset: (top: 6pt),
    above: 1.6em,
    below: 1.0em
  )[
    #if title != "" [
      #block(above: 0pt, below: 4pt)[
        #text(font: font-heading, weight: "medium", size: 8.8pt, fill: lukb-navy)[#title]
      ]
    ]
    #set par(leading: 0.35em, justify: false)
    #for it in items [
      #block(above: 0pt, below: 3pt)[
        #text(font: font-heading, weight: "medium", size: 7.5pt, fill: lukb-blue)[#it.num]
        #h(4pt)
        #text(font: font-body, weight: "light", size: 7.5pt, fill: lukb-muted)[#it.text]
      ]
    ]
  ]
}

#let render-glossary-box(title, items) = {
  if items.len() == 0 { return }
  block(
    width: 100%,
    stroke: (top: 0.8pt + lukb-navy),
    inset: (top: 6pt),
    above: 1.6em,
    below: 1.0em
  )[
    #if title != "" [
      #block(above: 0pt, below: 6pt)[
        #text(font: font-heading, weight: "medium", size: 8.8pt, fill: lukb-navy)[#title]
      ]
    ]
    #grid(
      columns: (1fr, 1fr),
      column-gutter: 14pt,
      row-gutter: 4pt,
      ..items.map(it => [
        #set par(leading: 0.3em, justify: false)
        #text(font: font-heading, weight: "medium", size: 7.8pt, fill: lukb-navy)[#it.term]
        #text(font: font-body, weight: "light", size: 7.5pt, fill: lukb-muted)[: #it.definition]
      ])
    )
  ]
}

#let render-publications-box(title, items) = {
  let active-items = items.filter(it => it.at("enabled", default: true))
  if active-items.len() == 0 { return }
  block(
    width: 100%,
    stroke: (top: 0.8pt + lukb-navy),
    inset: (top: 6pt),
    above: 1.6em,
    below: 1.0em
  )[
    #if title != "" [
      #block(above: 0pt, below: 6pt)[
        #text(font: font-heading, weight: "medium", size: 8.8pt, fill: lukb-navy)[#title]
      ]
    ]
    #grid(
      columns: (1fr, 1fr),
      column-gutter: 14pt,
      row-gutter: 4pt,
      ..active-items.map(item => {
        let clean-title = item.title
        let pdate = item.at("formatted_date", default: item.at("date", default: ""))
        let purl = str(item.at("url", default: "")).trim()
        let line-text = [
          #text(font: font-heading, weight: "medium", size: 8.2pt, fill: lukb-navy)[\"#clean-title\"]#if pdate != "" [ vom #text(font: font-body, weight: "light", size: 8.2pt, fill: lukb-navy)[#pdate]]#if purl != "" [ #box(baseline: -0.05em)[#text(size: 0.8em, fill: lukb-blue)[#sym.arrow.tr]]]
        ]
        block[
          #set par(justify: false, leading: 0.35em)
          #if purl != "" { link(purl)[#line-text] } else { line-text }
        ]
      })
    )
  ]
}

#let build-tufte-grid-rows(items) = {
  let rows = ()
  let curr-left = ()
  let pending-right = ()

  for it in items {
    let is-margin = (it.type in ("figure", "db_chart", "table")) and (it.at("layout", default: "column") == "column")
    if is-margin {
      // Wenn bereits Text VOR diesem Rand-Element existiert, schließen wir
      // die vorherige Zeile ab, damit das Rand-Element genau auf Höhe des
      // DANACH im Editor folgenden Absatzes platziert wird.
      if curr-left.len() > 0 {
        rows.push((left: curr-left, right: pending-right))
        curr-left = ()
        pending-right = ()
      }
      pending-right.push(it)
    } else {
      curr-left.push(it)
    }
  }

  if curr-left.len() > 0 or pending-right.len() > 0 {
    rows.push((left: curr-left, right: pending-right))
  }
  return rows
}

// Einzelner Block-Renderer
#let render-single-block(blk, is-margin: false) = {
  if blk.type == "heading" {
    render-heading(blk.level, blk.text)
  } else if blk.type == "richtext" {
    eval(blk.typst_markup, mode: "markup")
    parbreak()
  } else if blk.type == "callout" {
    render-callout(blk.title, blk.typst_markup)
  } else if blk.type in ("figure", "db_chart") {
    render-figure-box(blk, is-margin: is-margin)
  } else if blk.type == "table" {
    render-table-box(blk, is-margin: is-margin)
  } else if blk.type == "textbox_group" {
    let visual-children = blk.children.filter(c => c.type in ("figure", "db_chart", "table"))
    let text-children = blk.children.filter(c => not (c.type in ("figure", "db_chart", "table")))
    let has-visuals = visual-children.len() > 0
    let has-text = text-children.len() > 0
    let is-split = has-visuals and has-text and (not is-margin)

    block(
      width: 100%,
      fill: rgb("#EBF3FA"),
      stroke: 0.6pt + lukb-navy,
      inset: (x: 10pt, y: 9pt),
      radius: 2pt,
      above: 1.25em,
      below: 1.25em
    )[
      #if is-split [
        #let box-rows = build-tufte-grid-rows(blk.children)
        #let box-gutters = if box-rows.len() > 1 {
          box-rows.slice(1).map(r => {
            if r.left.len() > 0 {
              let first-it = r.left.at(0)
              if first-it.type == "heading" {
                let lvl = first-it.at("level", default: 2)
                if lvl == 1 { 2.1em } else { 1.85em }
              } else if first-it.type == "richtext" {
                1.6em
              } else {
                1.6em
              }
            } else {
              1.6em
            }
          })
        } else {
          1.6em
        }

        #grid(
          columns: (1fr, 56mm),
          column-gutter: 8mm,
          row-gutter: box-gutters,
          ..box-rows.map(r => (
            [
              #for l-it in r.left [
                #render-single-block(l-it, is-margin: false)
              ]
            ],
            [
              #if r.right.len() > 0 [
                #stack(
                  spacing: 8pt,
                  ..r.right.map(r-it => render-single-block(r-it, is-margin: true))
                )
              ]
            ]
          )).flatten()
        )
      ] else [
        #for child in blk.children [
          #render-single-block(child, is-margin: is-margin)
        ]
      ]
    ]
  } else if blk.type == "spacer" {
    let h-mm = blk.at("height_mm", default: 8)
    v(h-mm * 1mm)
  } else if blk.type == "colbreak" {
    // Spalten- bzw. Seitenumbruch wird auf Run-Ebene außerhalb von Containern gerendert
  } else if blk.type == "quote" {
    render-quote-box(
      blk.at("quote_typst", default: blk.at("quote", default: "")),
      blk.at("author_typst", default: blk.at("author", default: "")),
      blk.at("source_typst", default: blk.at("source", default: "")),
      is-margin: is-margin
    )
  } else if blk.type == "divider" {
    render-divider(blk.at("style", default: "solid"))
  } else if blk.type == "footnotes" {
    render-footnotes-box(
      blk.at("title_typst", default: blk.at("title", default: "Anmerkungen & Quellen")),
      blk.at("items_typst", default: blk.at("items", default: ()))
    )
  } else if blk.type == "glossary" {
    render-glossary-box(
      blk.at("title_typst", default: blk.at("title", default: "Glossar & Begriffserklärungen")),
      blk.at("items_typst", default: blk.at("items", default: ()))
    )
  } else if blk.type == "publications" {
    render-publications-box(
      blk.at("title_typst", default: blk.at("title", default: "Weitere Publikationen")),
      blk.at("items_typst", default: blk.at("items", default: ()))
    )
  }
}

// ============================================================================
// Dokumenten-Kopf (Exakt wie LUKB Investment Fokus)
// ============================================================================

#v(-0.75cm)

#block(
  width: 100%,
  inset: (bottom: 12pt),
  stroke: (bottom: 1.5pt + lukb-navy)
)[
  #grid(
    columns: (1fr, auto),
    align(left + top)[
      #image("LUKB-Logo.svg", height: 30pt)
    ],
    align(right + top)[
      #pad(top: 3.5pt)[
        #let raw-header-series = meta.at("header_series", default: none)
        #let header-series-text = if raw-header-series != none and raw-header-series != "" { raw-header-series } else { "Investment Office News" }
        #text(font: font-heading, weight: "medium", size: 14pt, fill: rgb("#0093D1"))[
          #header-series-text
        ]
      ]
    ]
  )

  #v(14pt)

  #let sub-line = if meta.subtitle != "" { meta.subtitle } else if meta.at("category", default: "") != "" { meta.category } else { "" }
  #let display-date = format-pub-date(meta.publication_date)

  #if sub-line != "" or display-date != "" [
    #grid(
      columns: (1fr, auto),
      gutter: 10pt,
      align(left + bottom)[
        #if sub-line != "" [
          #text(font: font-heading, weight: "medium", size: 10.5pt, fill: lukb-blue)[#sub-line]
        ]
      ],
      align(right + bottom)[
        #if display-date != "" [
          #text(font: font-body, weight: "light", size: 11pt, fill: lukb-muted)[#display-date]
        ]
      ]
    )
    #v(4pt)
  ]

  #block(above: 12pt, below: 2.2em)[
    #align(left)[
      #set par(justify: false, leading: 0.42em)
      #set text(hyphenate: false)
      #text(font: font-heading, weight: "medium", size: 22pt, fill: lukb-navy)[#meta.title]
    ]
  ]

  #if meta.lead != "" [
    #block(above: 0pt, below: 2.2em)[
      #align(left)[
        #set par(justify: false, leading: 0.68em)
        #text(font: font-body, weight: "light", size: 10.8pt, fill: lukb-text)[
          #eval(meta.lead_typst, mode: "markup")
        ]
      ]
    ]
  ]

  #if meta.authors.len() > 0 [
    #block(
      width: 100%,
      fill: lukb-surface,
      inset: (x: 10pt, y: 6pt),
      radius: 2pt
    )[
      #text(font: font-heading, weight: "medium", size: 8pt, fill: lukb-navy)[Autoren: ]
      #h(4pt)
      #for (idx, a) in meta.authors.enumerate() [
        #if idx > 0 [ #text(fill: lukb-muted)[ · ] ]
        #text(font: font-heading, weight: "medium", size: 8.2pt, fill: lukb-text)[#a.name]
        #if a.role != "" [
          #text(font: font-body, weight: "light", size: 8pt, fill: lukb-muted)[ (#a.role)]
        ]
      ]
    ]
  ]

  #if meta.at("tags", default: ()).len() > 0 [
    #v(6pt)
    #stack(
      dir: ltr,
      spacing: 5pt,
      ..meta.tags.map(tag => box(
        fill: rgb("#F1F5F9"),
        stroke: 0.5pt + rgb("#CBD5E1"),
        radius: 2pt,
        inset: (x: 5pt, y: 2.5pt),
        outset: 0pt,
        baseline: 0%,
        [#text(font: font-heading, size: 7.5pt, weight: "medium", fill: lukb-navy)[#tag]]
      ))
    )
  ]
]

#v(8pt)

// ============================================================================
// Asymmetrischer Tufte-Hauptteil
// Hauptspalte: 116mm, Steg: 8mm, Randbereich: 56mm (Total = 180mm)
// ============================================================================

#let tufte-main-w = 116mm
#let tufte-gutter = 8mm
#let tufte-margin-w = 56mm

#let build-tufte-runs(items) = {
  let runs = ()
  let curr-grid-items = ()

  for blk in items {
    if blk.type == "colbreak" {
      if curr-grid-items.len() > 0 {
        runs.push((kind: "grid", items: curr-grid-items))
        curr-grid-items = ()
      }
      runs.push((kind: "break"))
    } else {
      let has-box-visuals = (blk.type == "textbox_group") and blk.children.any(c => c.type in ("figure", "db_chart", "table"))
      let is-full = ((blk.type in ("figure", "db_chart", "table", "quote", "footnotes", "glossary", "publications")) and (blk.at("layout", default: "column") == "full")) or ((blk.type == "textbox_group") and (has-box-visuals or blk.at("layout", default: "column") == "full"))
      if is-full {
        if curr-grid-items.len() > 0 {
          runs.push((kind: "grid", items: curr-grid-items))
          curr-grid-items = ()
        }
        runs.push((kind: "full", item: blk))
      } else {
        curr-grid-items.push(blk)
      }
    }
  }

  if curr-grid-items.len() > 0 {
    runs.push((kind: "grid", items: curr-grid-items))
  }
  return runs
}

#let runs = build-tufte-runs(blocks)

#for run in runs {
  if run.kind == "break" {
    pagebreak(weak: true)
  } else if run.kind == "full" {
    block(width: 100%)[
      #render-single-block(run.item, is-margin: false)
    ]
  } else {
    let rows = build-tufte-grid-rows(run.items)
    let gutters = if rows.len() > 1 {
      rows.slice(1).map(r => {
        if r.left.len() > 0 {
          let first-it = r.left.at(0)
          if first-it.type == "heading" {
            let lvl = first-it.at("level", default: 2)
            if lvl == 1 { 2.3em } else { 2.0em }
          } else if first-it.type == "richtext" {
            1.8em
          } else if first-it.type in ("callout", "textbox_group") {
            1.6em
          } else {
            1.8em
          }
        } else {
          1.8em
        }
      })
    } else {
      1.8em
    }

    grid(
      columns: (tufte-main-w, tufte-margin-w),
      column-gutter: tufte-gutter,
      row-gutter: gutters,
      ..rows.map(r => (
        [
          #for l-it in r.left [
            #render-single-block(l-it, is-margin: false)
          ]
        ],
        [
          #if r.right.len() > 0 [
            #stack(
              spacing: 10pt,
              ..r.right.map(r-it => render-single-block(r-it, is-margin: true))
            )
          ]
        ]
      )).flatten()
    )
  }
}
