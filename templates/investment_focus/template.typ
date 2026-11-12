// ============================================================================
// LUKB Investment Fokus — Zweispaltiges Publikations-Template (Typst 0.15+)
// Standard-Schriftart: Yoga Sans for LUKB Light
// Überschriften-Schriftart: Yoga Sans for LUKB Medium
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
  spacing: 2.0em
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
    } else if page-num == 1 {
      align(top)[
        #block(
          width: 100%,
          inset: (top: 5pt),
          stroke: (top: 0.5pt + lukb-border)
        )[
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
  let sz = if level == 1 { 14.5pt } else if level == 2 { 10.8pt } else { 9.8pt }
  let col = if level == 1 { lukb-navy } else if level == 2 { lukb-blue } else { lukb-text }
  let lead = if level == 1 { 0.42em } else if level == 2 { 0.38em } else { 0.34em }
  let abv = 2.0em
  let blw = if level == 1 { 6.5pt } else { 0.68em }
  if level == 1 {
    block(
      width: 100%,
      sticky: true,
      breakable: false,
      above: abv,
      below: blw
    )[
      #stack(
        spacing: 4.5pt,
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
    inset: (x: 11pt, y: 10pt),
    radius: (right: 3pt),
    above: 1em,
    below: 1.1em
  )[
    #if title != "" [
      #block(above: 0pt, below: 1.0em)[
        #text(font: font-heading, weight: "medium", size: 10pt, fill: lukb-navy)[#title]
      ]
    ]
    #set text(size: 9pt)
    #set par(spacing: 1.0em)
    #set list(spacing: 0.65em)
    #eval(markup-str, mode: "markup")
  ]
}

#let place-full-float(blk, box-el) = {
  let pos-mode = blk.at("full_position", default: "auto")
  if pos-mode == "top" {
    place(top, scope: "parent", float: true, clearance: 14pt, box-el)
  } else if pos-mode == "bottom" {
    place(bottom, scope: "parent", float: true, clearance: 14pt, box-el)
  } else {
    context {
      let auto-pos = if here().page() == 1 { bottom } else { top }
      place(auto-pos, scope: "parent", float: true, clearance: 14pt, box-el)
    }
  }
}

#let render-figure-box(blk) = {
  let is-floating = (blk.at("layout", default: "column") == "full") and not blk.at("_inline_full", default: false)
  let fig-box = block(
    width: 100%,
    breakable: false,
    stroke: (top: 1.5pt + lukb-navy, bottom: 0.6pt + lukb-border),
    inset: (top: 7pt, bottom: 6pt),
    above: if is-floating { 0pt } else { 2.0em },
    below: if is-floating { 0pt } else { 1.1em }
  )[
    #if blk.title != "" [
      #block(above: 0pt, below: if blk.subtitle != "" { 5.5pt } else { 6pt })[
        #set par(leading: 0.28em, justify: false)
        #text(font: font-heading, weight: "medium", size: 10pt, fill: lukb-navy)[#blk.title]
      ]
    ]
    #if blk.subtitle != "" [
      #block(above: 0pt, below: 6pt)[
        #set par(leading: 0.28em, justify: false)
        #text(font: font-body, weight: "light", size: 8.3pt, fill: lukb-muted)[#blk.subtitle]
      ]
    ]
    #if blk.resolved_image != "" [
      #align(center)[
        #image(blk.resolved_image, width: 100%)
      ]
    ] else [
      #rect(
        width: 100%,
        height: 95pt,
        fill: lukb-surface,
        stroke: (paint: lukb-border, dash: "dashed")
      )[
        #align(center + horizon)[
          #text(size: 8.5pt, fill: lukb-muted)[Grafik-Platzhalter (Bitte SVG oder PNG im Editor hochladen)]
        ]
      ]
    ]
    #if blk.source != "" [
      #v(2pt)
      #text(font: font-body, weight: "light", size: 7.5pt, fill: lukb-muted)[#blk.source]
    ]
  ]

  if is-floating {
    place-full-float(blk, fig-box)
  } else {
    fig-box
  }
}

#let render-table-box(blk) = {
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

  let is-floating = (blk.at("layout", default: "column") == "full") and not blk.at("_inline_full", default: false)
  let can-break = not is-floating

  let tbl-box = block(
    width: 100%,
    breakable: can-break,
    above: if is-floating { 0pt } else { 1.1em },
    below: if is-floating { 0pt } else { 1.1em }
  )[
    #block(
      width: 100%,
      sticky: true,
      breakable: false,
      stroke: (top: 1.5pt + lukb-navy),
      inset: (top: 7pt),
      above: 0pt,
      below: if blk.title != "" or blk.subtitle != "" { 6pt } else { 2pt }
    )[
      #if blk.title != "" [
        #block(above: 0pt, below: if blk.subtitle != "" { 5.5pt } else { 0pt })[
          #set par(leading: 0.28em, justify: false)
          #text(font: font-heading, weight: "medium", size: 10pt, fill: lukb-navy)[#blk.title]
        ]
      ]
      #if blk.subtitle != "" [
        #block(above: 0pt, below: 0pt)[
          #set par(leading: 0.28em, justify: false)
          #text(font: font-body, weight: "light", size: 8.3pt, fill: lukb-muted)[#blk.subtitle]
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
        bottom: if show-header {
          if y == rows.len() { 0.8pt + lukb-navy } else { 0.4pt + lukb-border }
        } else {
          if rows.len() > 0 and y == rows.len() - 1 { 0.8pt + lukb-navy } else { 0.4pt + lukb-border }
        }
      ),
      fill: (x, y) => {
        if show-header {
          if y == 0 { lukb-navy }
          else if blk.highlight_last_row and y == rows.len() { rgb("#E6EEF7") }
          else if calc.even(y) { lukb-surface }
          else { white }
        } else {
          if rows.len() > 0 and blk.highlight_last_row and y == rows.len() - 1 { rgb("#E6EEF7") }
          else if calc.odd(y) { lukb-surface }
          else { white }
        }
      },
      inset: (x: 6pt, y: 5pt),
      ..(if show-header {
        (
          table.header(
            repeat: true,
            ..cols.map(c => text(font: font-heading, weight: "medium", size: 8.2pt, fill: white)[#c.title]),
          ),
        )
      } else {
        ()
      }),
      ..for (r-idx, row-dict) in rows.enumerate() {
        let is-total = blk.highlight_last_row and (r-idx == rows.len() - 1)
        cols.map(c => {
          let cell-val = row-dict.at(c.field, default: "")
          if is-total {
            text(font: font-heading, weight: "medium", size: 8.3pt, fill: lukb-navy)[#cell-val]
          } else {
            text(font: font-body, weight: "light", size: 8.3pt, fill: lukb-text)[#cell-val]
          }
        })
      }
    )

    #block(
      width: 100%,
      breakable: false,
      stroke: (bottom: 0.6pt + lukb-border),
      inset: (top: if blk.source != "" { 4pt } else { 0pt }, bottom: 6pt),
      above: 0pt,
      below: 0pt
    )[
      #if blk.source != "" [
        #text(font: font-body, weight: "light", size: 7.5pt, fill: lukb-muted)[#blk.source]
      ]
    ]
  ]

  if is-floating {
    place-full-float(blk, tbl-box)
  } else {
    tbl-box
  }
}

#let render-quote-box(quote-text, author, source) = {
  block(
    width: 100%,
    breakable: false,
    stroke: (left: 3pt + lukb-cyan),
    fill: rgb("#F8FAFC"),
    inset: (left: 11pt, right: 8pt, y: 7pt),
    radius: (right: 2pt),
    above: 1.1em,
    below: 1.1em
  )[
    #set par(leading: 0.38em)
    #text(font: font-heading, style: "italic", size: 10.2pt, fill: lukb-navy)[
      #quote-text
    ]
    #if author != "" or source != "" [
      #v(4pt)
      #if author != "" [
        #text(font: font-heading, weight: "medium", size: 8.5pt, fill: lukb-navy)[#author]
      ]
      #if author != "" and source != "" [
        #text(size: 8.5pt, fill: lukb-muted)[ · ]
      ]
      #if source != "" [
        #text(font: font-body, weight: "light", size: 8pt, fill: lukb-muted)[#source]
      ]
    ]
  ]
}

#let render-divider(style) = {
  let dash-pattern = if style == "dashed" { "dashed" } else if style == "dots" { "dotted" } else { none }
  block(
    width: 100%,
    above: 1.2em,
    below: 1.2em,
    line(
      length: 100%,
      stroke: (paint: lukb-border, thickness: 0.75pt, dash: dash-pattern)
    )
  )
}

#let render-footnotes-box(title, items) = {
  block(
    width: 100%,
    breakable: false,
    stroke: (top: 0.8pt + lukb-border),
    inset: (top: 6pt, bottom: 4pt),
    above: 1.3em,
    below: 1.1em
  )[
    #if title != "" [
      #text(font: font-heading, weight: "medium", size: 10.8pt, fill: lukb-blue)[#title]
      #v(4pt)
    ]
    #for item in items [
      #let num = item.at("num", default: "")
      #let txt = item.at("text", default: "")
      #block(above: 2pt, below: 2pt)[
        #set par(leading: 0.28em)
        #if num != "" [
          #text(font: font-heading, weight: "medium", size: 7.5pt, fill: lukb-cyan)[\[#num\] ]
        ]
        #text(font: font-body, weight: "light", size: 7.5pt, fill: lukb-muted)[#txt]
      ]
    ]
  ]
}

#let render-glossary-box(title, items) = {
  if items.len() > 0 [
    #block(
      width: 100%,
      breakable: false,
      stroke: (top: 0.8pt + lukb-border),
      inset: (top: 7pt, bottom: 5pt),
      above: 1.3em,
      below: 1.1em
    )[
      #if title != "" [
        #text(font: font-heading, weight: "medium", size: 10.8pt, fill: lukb-blue)[#title]
        #v(5pt)
      ]
      #for item in items [
        #let term = item.at("term", default: "")
        #let def = item.at("definition", default: "")
        #block(above: 2.5pt, below: 2.5pt)[
          #set par(leading: 0.28em)
          #text(font: font-heading, weight: "medium", size: 7.8pt, fill: lukb-navy)[#term]
          #h(3pt)
          #text(font: font-body, weight: "light", size: 7.6pt, fill: lukb-muted)[—]
          #h(3pt)
          #text(font: font-body, weight: "light", size: 7.6pt, fill: lukb-text)[#def]
        ]
      ]
    ]
  ]
}

#let render-publications-box(title, items) = {
  let active-items = items.filter(it => it.at("enabled", default: true))
  if active-items.len() > 0 [
    #block(
      width: 100%,
      breakable: false,
      stroke: (top: 1.2pt + lukb-navy, bottom: 0.6pt + lukb-border),
      inset: (top: 7pt, bottom: 7pt),
      above: 2.0em,
      below: 1.5em
    )[
      #if title != "" [
        #block(above: 0pt, below: 8pt)[
          #text(font: font-heading, weight: "medium", size: 10.8pt, fill: lukb-navy)[#title]
        ]
      ]
      #stack(
        spacing: 5pt,
        ..active-items.map(item => {
          let raw-title = item.at("title", default: "").trim()
          let clean-title = raw-title
          if clean-title.starts-with("\"") and clean-title.ends-with("\"") and clean-title.len() >= 2 {
            clean-title = clean-title.slice(1, clean-title.len() - 1)
          }
          if clean-title.starts-with("«") and clean-title.ends-with("»") and clean-title.len() >= 2 {
            clean-title = clean-title.slice(1, clean-title.len() - 1)
          }
          let pdate = item.at("formatted_date", default: item.at("date", default: ""))
          let purl = str(item.at("url", default: "")).trim()

          let line-text = [
            #text(font: font-heading, weight: "medium", size: 8.5pt, fill: lukb-navy)[\"#clean-title\"]#if pdate != "" [ vom #text(font: font-body, weight: "light", size: 8.5pt, fill: lukb-navy)[#pdate]]#if purl != "" [ #box(baseline: -0.05em)[#text(size: 0.8em, fill: lukb-blue)[#sym.arrow.tr]]]
          ]

          block[
            #set par(justify: false, leading: 0.35em)
            #if purl != "" {
              link(purl)[#line-text]
            } else {
              line-text
            }
          ]
        })
      )
    ]
  ]
}

// ============================================================================
// Dokumenten-Kopf (Seite 1 Banner, Gesamttitel, Lead, Autoren)
// Auf Seite 1 Ausgleich von 0.75cm, sodass Seite 1 bei 1.25cm beginnt und Folgeseiten bei 2cm
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

  #block(above: 12pt, below: 3em)[
    #align(left)[
      #set par(justify: false, leading: 0.42em)
      #set text(hyphenate: false)
      #text(font: font-heading, weight: "medium", size: 22pt, fill: lukb-navy)[#meta.title]
    ]
  ]

  #if meta.lead != "" [
    #block(above: 0pt, below: 3em)[
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
// Zweispaltiger Hauptteil mit automatischem Spaltenausgleich (Column Balancing)
// & Zusammenhalt für farbliche Textboxen
// ============================================================================

#let render-single-block(blk, in-box: false, inline-full: false) = {
  if blk.type == "heading" {
    render-heading(blk.level, blk.text)
  } else if blk.type == "richtext" {
    eval(blk.typst_markup, mode: "markup")
    parbreak()
  } else if blk.type == "callout" {
    render-callout(blk.title, blk.typst_markup)
  } else if blk.type in ("figure", "db_chart") {
    let bcopy = blk
    if in-box {
      bcopy.insert("layout", "column")
    } else if inline-full {
      bcopy.insert("_inline_full", true)
    }
    render-figure-box(bcopy)
  } else if blk.type == "table" {
    let bcopy = blk
    if in-box {
      bcopy.insert("layout", "column")
    } else if inline-full {
      bcopy.insert("_inline_full", true)
    }
    render-table-box(bcopy)
  } else if blk.type == "textbox_group" {
    layout(bounds => {
      let inner-content = [
        #for child in blk.children [
          #render-single-block(child, in-box: true)
        ]
      ]
      let box-breakable = block(
        width: 100%,
        breakable: true,
        fill: rgb("#EBF3FA"),
        stroke: 0.6pt + lukb-navy,
        inset: (x: 10pt, y: 9pt),
        radius: 2pt,
        above: 1.05em,
        below: 1.05em,
        inner-content
      )
      let box-h = measure(box-breakable, width: bounds.width).height
      // Farbliche Boxen bis zu einer Spaltenhöhe bleiben als geschlossene Einheit zusammen
      if box-h <= 460pt {
        block(
          width: 100%,
          breakable: false,
          fill: rgb("#EBF3FA"),
          stroke: 0.6pt + lukb-navy,
          inset: (x: 10pt, y: 9pt),
          radius: 2pt,
          above: 1.05em,
          below: 1.05em,
          inner-content
        )
      } else {
        box-breakable
      }
    })
  } else if blk.type == "spacer" {
    let h-mm = blk.at("height_mm", default: 8)
    v(h-mm * 1mm)
  } else if blk.type == "colbreak" {
    colbreak()
  } else if blk.type == "quote" {
    let q-box = render-quote-box(
      blk.at("quote_typst", default: blk.at("quote", default: "")),
      blk.at("author_typst", default: blk.at("author", default: "")),
      blk.at("source_typst", default: blk.at("source", default: ""))
    )
    if blk.at("layout", default: "column") == "full" and not in-box and not inline-full {
      place(bottom, scope: "parent", float: true, q-box)
    } else {
      q-box
    }
  } else if blk.type == "divider" {
    render-divider(blk.at("style", default: "solid"))
  } else if blk.type == "footnotes" {
    let fn-box = render-footnotes-box(
      blk.at("title_typst", default: blk.at("title", default: "Anmerkungen & Quellen")),
      blk.at("items_typst", default: blk.at("items", default: ()))
    )
    if blk.at("layout", default: "column") == "full" and not in-box and not inline-full {
      place(bottom, scope: "parent", float: true, fn-box)
    } else {
      fn-box
    }
  } else if blk.type == "glossary" {
    let g-box = render-glossary-box(
      blk.at("title_typst", default: blk.at("title", default: "Glossar & Begriffserklärungen")),
      blk.at("items_typst", default: blk.at("items", default: ()))
    )
    if blk.at("layout", default: "column") == "full" and not in-box and not inline-full {
      place(bottom, scope: "parent", float: true, g-box)
    } else {
      g-box
    }
  } else if blk.type == "publications" {
    let pub-box = render-publications-box(
      blk.at("title_typst", default: blk.at("title", default: "Weitere Publikationen")),
      blk.at("items_typst", default: blk.at("items", default: ()))
    )
    if blk.at("layout", default: "column") == "full" and not in-box and not inline-full {
      place(bottom, scope: "parent", float: true, pub-box)
    } else {
      pub-box
    }
  }
}

#let render-balanced-col-run(items, gutter: 16pt) = context {
  let start-pos = here().position()
  layout(bounds => {
    let col-w = (bounds.width - gutter) / 2
    let page-h = 841.89pt
    let bottom-margin = 2.4cm
    let avail-h = page-h - start-pos.y - bottom-margin

    let has-full-float = items.any(it => (it.type in ("figure", "db_chart", "table")) and (it.at("layout", default: "column") == "full"))
    let manual-colbreak-idx = items.position(it => it.type == "colbreak")
    if has-full-float {
      columns(2, gutter: gutter)[
        #for it in items [
          #render-single-block(it, in-box: false)
        ]
      ]
    } else if manual-colbreak-idx != none and avail-h > 100pt {
      let left-items = items.slice(0, manual-colbreak-idx)
      let right-items = items.slice(manual-colbreak-idx + 1)
      let left-h = measure(block(width: col-w, for it in left-items [ #render-single-block(it, in-box: false) ])).height
      let right-h = measure(block(width: col-w, for it in right-items [ #render-single-block(it, in-box: false) ])).height
      let max-h = calc.max(left-h, right-h)
      if max-h <= avail-h - 6pt {
        grid(
          columns: (1fr, 1fr),
          column-gutter: gutter,
          align: (top + left, top + left),
          [
            #for it in left-items [ #render-single-block(it, in-box: false) ]
          ],
          [
            #for it in right-items [ #render-single-block(it, in-box: false) ]
          ]
        )
      } else {
        columns(2, gutter: gutter)[
          #for it in items [
            #render-single-block(it, in-box: false)
          ]
        ]
      }
    } else {
      // 1. Suche nach dem optimalen Trennpunkt zwischen eigenständigen Blöcken.
      // Typografische Grundregel: Niemals direkt nach einer Überschrift trennen!
      // Bei Gleichstand oder geringem Unterschied soll die linke Spalte mindestens so lang wie die rechte sein.
      let best-split-idx = 0
      let best-score = 999999pt
      let best-max-h = 999999pt

      if items.len() >= 2 {
        for split-idx in range(1, items.len()) {
          let prev-is-heading = (items.at(split-idx - 1).type == "heading")
          if not prev-is-heading {
            let left-items = items.slice(0, split-idx)
            let right-items = items.slice(split-idx)
            let left-h = measure(block(width: col-w, for it in left-items [ #render-single-block(it, in-box: false) ])).height
            let right-h = measure(block(width: col-w, for it in right-items [ #render-single-block(it, in-box: false) ])).height
            let diff = calc.abs(left-h - right-h)
            let max-h = calc.max(left-h, right-h)
            let right-heavy-penalty = if right-h > left-h + 2pt { 60pt } else { 0pt }
            let score = diff + right-heavy-penalty
            if score < best-score {
              best-score = score
              best-split-idx = split-idx
              best-max-h = max-h
            }
          }
        }
      }

      // Wenn ein sauberer Block-Split gefunden wird, der auf die Seite passt:
      // Rendere als 2-spaltiges Grid. Dadurch werden NIE Wörter oder Absätze
      // über die Spaltengrenze hinweg zerrissen und die Spalten sind perfekt balanciert!
      let page-body-h = page-h - 2cm - bottom-margin
      if best-split-idx > 0 and ((avail-h > 80pt and best-max-h <= (avail-h + 10pt)) or (avail-h <= 80pt and best-max-h <= page-body-h)) {
        if avail-h <= 80pt {
          pagebreak(weak: true)
        }
        let left-items = items.slice(0, best-split-idx)
        let right-items = items.slice(best-split-idx)
        grid(
          columns: (1fr, 1fr),
          column-gutter: gutter,
          align: (top + left, top + left),
          [
            #for it in left-items [ #render-single-block(it, in-box: false) ]
          ],
          [
            #for it in right-items [ #render-single-block(it, in-box: false) ]
          ]
        )
      } else {
        // Fallback für mehrseitige Texte oder wenn nur ein einzelner Block vorliegt:
        let has-table = items.any(it => it.type == "table")
        let total-h = measure(block(width: col-w, for it in items [ #render-single-block(it, in-box: false) ])).height
        let ideal-half = total-h / 2 + 16pt
        let target-h = calc.max(ideal-half, best-max-h + 6pt)

        if not has-table and avail-h > 100pt and target-h <= (avail-h - 6pt) {
          block(
            width: 100%,
            height: target-h,
            columns(2, gutter: gutter)[
              #for it in items [
                #render-single-block(it, in-box: false)
              ]
            ]
          )
        } else {
          columns(2, gutter: gutter)[
            #for it in items [
              #render-single-block(it, in-box: false)
            ]
          ]
        }
      }
    }
  })
}

#let render-col-run-smart(items, bounds, max-float-h: 520pt, gutter: 16pt) = context {
  let start-pos = here().position()
  let col-w = (bounds.width - gutter) / 2
  let page-h = 841.89pt
  let top-margin = 2cm
  let bottom-margin = 2.4cm
  let page-body-h = page-h - top-margin - bottom-margin
  let avail-h = calc.max(0pt, page-h - start-pos.y - bottom-margin)

  let has-full-table = items.any(it => it.type == "table" and it.at("layout", default: "column") == "full")
  if not has-full-table {
    render-balanced-col-run(items, gutter: gutter)
  } else {
    let used-h = 0pt
    let pending-col-items = ()
    let overflow-idx = none

    let flush-col-h = (col-items) => {
      if col-items.len() == 0 {
        0pt
      } else {
        let h = measure(block(width: col-w, for c-it in col-items [ #render-single-block(c-it, in-box: false) ])).height
        let max-indiv-h = 0pt
        for c-it in col-items {
          if c-it.type in ("figure", "db_chart", "callout", "quote") {
            let ih = measure(block(width: col-w, render-single-block(c-it, in-box: false))).height
            if ih > max-indiv-h { max-indiv-h = ih }
          }
        }
        calc.max(h / 2 + 8pt, max-indiv-h + 8pt)
      }
    }

    for (idx, it) in items.enumerate() {
      let is-full = (it.type in ("figure", "db_chart", "table")) and (it.at("layout", default: "column") == "full")
      if not is-full {
        pending-col-items.push(it)
      } else {
        used-h = used-h + flush-col-h(pending-col-items)
        pending-col-items = ()

        let b-probe = it
        b-probe.insert("_inline_full", true)
        let box-h = if it.type == "table" {
          measure(block(width: bounds.width, render-table-box(b-probe))).height
        } else {
          measure(block(width: bounds.width, render-figure-box(b-probe))).height
        }

        if it.type == "table" {
          let rem-h = if used-h <= avail-h {
            avail-h - used-h
          } else {
            let spill = used-h - avail-h
            page-body-h - calc.rem(spill.pt(), page-body-h.pt()) * 1pt
          }
          if box-h > max-float-h or (box-h + 14pt) > rem-h {
            overflow-idx = idx
            break
          }
        }
        used-h = used-h + box-h + 14pt
      }
    }

    if overflow-idx == none {
      render-balanced-col-run(items, gutter: gutter)
    } else {
      if overflow-idx > 0 {
        render-balanced-col-run(items.slice(0, overflow-idx), gutter: gutter)
      }
      render-single-block(items.at(overflow-idx), in-box: false, inline-full: true)
      if overflow-idx + 1 < items.len() {
        render-col-run-smart(items.slice(overflow-idx + 1), bounds, max-float-h: max-float-h, gutter: gutter)
      }
    }
  }
}

#layout(bounds => {
  let max-float-h = 520pt
  let runs = ()
  let curr-cols = ()
  for blk in blocks {
    let is-full-block = (blk.type in ("figure", "db_chart", "table")) and (blk.at("layout", default: "column") == "full")
    let is-inline-full = false
    if is-full-block {
      let pos-mode = blk.at("full_position", default: "auto")
      if pos-mode == "inline" {
        is-inline-full = true
      } else if blk.type == "table" {
        let b-probe = blk
        b-probe.insert("_inline_full", true)
        let measured-h = measure(block(width: bounds.width, render-table-box(b-probe))).height
        if measured-h > max-float-h {
          is-inline-full = true
        }
      }
    }

    if is-inline-full {
      if curr-cols.len() > 0 {
        runs.push((kind: "cols", items: curr-cols))
        curr-cols = ()
      }
      runs.push((kind: "full", item: blk))
    } else {
      curr-cols.push(blk)
    }
  }
  if curr-cols.len() > 0 {
    runs.push((kind: "cols", items: curr-cols))
  }

  for run in runs {
    if run.kind == "full" {
      render-single-block(run.item, in-box: false, inline-full: true)
    } else {
      render-col-run-smart(run.items, bounds, max-float-h: max-float-h, gutter: 16pt)
    }
  }
})
