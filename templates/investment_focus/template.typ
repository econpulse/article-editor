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
  let blw = if level == 1 { 0.85em } else { 0.68em }
  block(
    sticky: true,
    breakable: false,
    above: abv,
    below: blw,
    stroke: if level == 1 { (bottom: 0.75pt + lukb-navy) } else { none },
    inset: (bottom: 0pt)
  )[
    #set text(hyphenate: false)
    #set par(leading: lead, justify: false)
    #text(font: font-heading, weight: "medium", size: sz, fill: col)[#content-text]
  ]
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

#let render-figure-box(blk) = {
  let fig-box = block(
    width: 100%,
    breakable: false,
    stroke: (top: 1.5pt + lukb-navy, bottom: 0.6pt + lukb-border),
    inset: (top: 7pt, bottom: 6pt),
    above: 2.0em,
    below: 1.1em
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

  if blk.layout == "full" and not blk.at("_inline_full", default: false) {
    place(
      bottom,
      scope: "parent",
      float: true,
      fig-box
    )
  } else {
    fig-box
  }
}

#let render-table-box(blk) = {
  let cols = blk.columns
  let rows = blk.rows
  let col-count = if cols.len() > 0 { cols.len() } else { 1 }

  let aligns = cols.map(c => {
    if c.align == "right" { right + horizon }
    else if c.align == "center" { center + horizon }
    else { left + horizon }
  })

  let col-widths = cols.enumerate().map(((idx, _)) => {
    if idx == 0 { 1.4fr } else { 1fr }
  })

  let tbl-box = block(
    width: 100%,
    breakable: false,
    stroke: (top: 1.5pt + lukb-navy, bottom: 0.6pt + lukb-border),
    inset: (top: 7pt, bottom: 6pt),
    above: 1.1em,
    below: 1.1em
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

    #table(
      columns: col-widths,
      align: aligns,
      stroke: (x, y) => (
        top: if y == 0 { 0.8pt + lukb-navy } else if y == 1 { 0.8pt + lukb-navy } else { 0.4pt + lukb-border },
        bottom: if y == rows.len() { 0.8pt + lukb-navy } else { 0pt }
      ),
      fill: (x, y) => {
        if y == 0 { lukb-navy }
        else if blk.highlight_last_row and y == rows.len() { rgb("#E6EEF7") }
        else if calc.even(y) { lukb-surface }
        else { white }
      },
      inset: (x: 6pt, y: 5pt),
      ..cols.map(c => text(font: font-heading, weight: "medium", size: 8.2pt, fill: white)[#c.title]),
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

    #if blk.source != "" [
      #v(4pt)
      #text(font: font-body, weight: "light", size: 7.5pt, fill: lukb-muted)[#blk.source]
    ]
  ]

  if blk.layout == "full" and not blk.at("_inline_full", default: false) {
    place(
      bottom,
      scope: "parent",
      float: true,
      tbl-box
    )
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
      stroke: (top: 1pt + lukb-blue, bottom: 0.6pt + lukb-border),
      inset: (top: 7pt, bottom: 6pt),
      above: 1.5em,
      below: 1.2em
    )[
      #if title != "" [
        #text(font: font-heading, weight: "medium", size: 10.8pt, fill: lukb-navy)[#title]
        #v(4pt)
      ]
      #for item in active-items [
        #let ptitle = item.at("title", default: "")
        #let psub = item.at("subtitle", default: "")
        #let pdate = item.at("date", default: "")
        #block(above: 3.5pt, below: 3.5pt)[
          #grid(
            columns: (1fr, auto),
            gutter: 6pt,
            text(font: font-heading, weight: "medium", size: 8pt, fill: lukb-navy)[#ptitle],
            if pdate != "" { text(font: font-body, size: 7.2pt, fill: lukb-muted)[#pdate] }
          )
          #if psub != "" [
            #block(above: 1pt, below: 0pt)[
              #text(font: font-body, weight: "light", size: 7.3pt, fill: lukb-muted)[#psub]
            ]
          ]
        ]
      ]
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
        #text(font: font-heading, weight: "medium", size: 14pt, fill: rgb("#0093D1"))[
          Investment Office News
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

    let manual-colbreak-idx = items.position(it => it.type == "colbreak")
    if manual-colbreak-idx != none and avail-h > 100pt {
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
      let best-split-idx = 0
      let best-diff = 999999pt
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
            if diff < best-diff {
              best-diff = diff
              best-split-idx = split-idx
              best-max-h = max-h
            }
          }
        }
      }

      // Wenn ein sauberer Block-Split gefunden wird, der auf die Seite passt:
      // Rendere als 2-spaltiges Grid. Dadurch werden NIE Wörter oder Absätze
      // über die Spaltengrenze hinweg zerrissen und die Spalten sind perfekt balanciert!
      if best-split-idx > 0 and avail-h > 80pt and best-max-h <= (avail-h + 10pt) {
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
        let total-h = measure(block(width: col-w, for it in items [ #render-single-block(it, in-box: false) ])).height
        let ideal-half = total-h / 2 + 16pt
        let target-h = calc.max(ideal-half, best-max-h + 6pt)

        if avail-h > 100pt and target-h <= (avail-h - 6pt) {
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

#{
  let runs = ()
  let curr-cols = ()
  for blk in blocks {
    let is-full = (blk.type in ("figure", "db_chart", "table")) and (blk.at("layout", default: "column") == "full")
    if is-full {
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
      render-balanced-col-run(run.items, gutter: 16pt)
    }
  }
}
