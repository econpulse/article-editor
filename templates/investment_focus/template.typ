// ============================================================================
// LUKB Investment Fokus — Zweispaltiges Publikations-Template (Typst 0.15+)
// Standard-Schriftart: Yoga Sans for LUKB Light
// Überschriften-Schriftart: Yoga Sans for LUKB Medium
// ============================================================================

#let payload = json(bytes(sys.inputs.at("article_json")))
#let meta = payload.metadata
#let blocks = payload.blocks

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
  spacing: 1.05em
)

#set page(
  paper: "a4",
  margin: (top: 2.3cm, bottom: 2.1cm, left: 1.8cm, right: 1.8cm),
  header: context {
    let page-num = counter(page).get().first()
    if page-num > 1 {
      block(width: 100%, inset: (bottom: 5pt), stroke: (bottom: 0.6pt + lukb-border))[
        #grid(
          columns: (1fr, auto),
          align(left)[
            #text(font: font-heading, weight: "medium", size: 8pt, fill: lukb-navy, tracking: 0.4pt)[
              LUKB INVESTMENT OFFICE
            ]
            #h(6pt)
            #text(size: 8pt, fill: lukb-muted)[| #meta.category]
          ],
          align(right)[
            #text(size: 8pt, fill: lukb-muted)[#meta.title]
          ]
        )
      ]
    }
  },
  footer: context {
    let page-num = counter(page).get().first()
    let total-pages = counter(page).final().first()
    block(width: 100%, inset: (top: 6pt), stroke: (top: 0.6pt + lukb-border))[
      #grid(
        columns: (1fr, auto),
        column-gutter: 12pt,
        align(left)[
          #text(size: 7pt, fill: lukb-muted)[#meta.disclaimer]
        ],
        align(right + horizon)[
          #text(font: font-heading, weight: "medium", size: 8pt, fill: lukb-navy)[
            Seite #page-num / #total-pages
          ]
        ]
      )
    ]
  }
)

// ============================================================================
// Komponenten-Bausteine
// ============================================================================

#let render-heading(level, content-text) = {
  let sz = if level == 1 { 12.5pt } else if level == 2 { 10.8pt } else { 9.8pt }
  let col = if level == 1 { lukb-navy } else if level == 2 { lukb-blue } else { lukb-text }
  block(
    sticky: true,
    breakable: false,
    above: 1.68em,
    below: 0.68em
  )[
    #set text(hyphenate: false)
    #set par(leading: 0.25em, justify: false)
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
      #text(font: font-heading, weight: "medium", size: 10pt, fill: lukb-navy)[#title]
      #v(4pt)
    ]
    #set text(size: 9pt)
    #eval(markup-str, mode: "markup")
  ]
}

#let render-figure-box(blk) = {
  let fig-box = block(
    width: 100%,
    breakable: false,
    stroke: (top: 1.5pt + lukb-navy, bottom: 0.6pt + lukb-border),
    inset: (top: 7pt, bottom: 6pt),
    above: 1.1em,
    below: 1.1em
  )[
    #if blk.title != "" [
      #text(font: font-heading, weight: "medium", size: 10pt, fill: lukb-navy)[#blk.title]
      #v(2pt)
    ]
    #if blk.subtitle != "" [
      #text(font: font-body, weight: "light", size: 8.3pt, fill: lukb-muted)[#blk.subtitle]
      #v(6pt)
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
      #v(4pt)
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
      #text(font: font-heading, weight: "medium", size: 10pt, fill: lukb-navy)[#blk.title]
      #v(2pt)
    ]
    #if blk.subtitle != "" [
      #text(font: font-body, weight: "light", size: 8.3pt, fill: lukb-muted)[#blk.subtitle]
      #v(6pt)
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

// ============================================================================
// Dokumenten-Kopf (Seite 1 Banner, Gesamttitel, Lead, Autoren)
// ============================================================================

#block(
  width: 100%,
  inset: (bottom: 12pt),
  stroke: (bottom: 1.5pt + lukb-navy)
)[
  #grid(
    columns: (1fr, auto),
    align(left + horizon)[
      #box(fill: lukb-navy, inset: (x: 8pt, y: 4pt), radius: 2pt)[
        #text(font: font-heading, weight: "medium", size: 8.5pt, fill: white, tracking: 0.8pt)[
          LUZERNER KANTONALBANK
        ]
      ]
      #h(8pt)
      #text(font: font-heading, weight: "medium", size: 9pt, fill: lukb-cyan, tracking: 0.4pt)[
        #upper(meta.category)
      ]
    ],
    align(right + horizon)[
      #text(font: font-body, weight: "light", size: 8.5pt, fill: lukb-muted)[
        Publikation vom #meta.publication_date
      ]
    ]
  )

  #v(10pt)

  #if meta.subtitle != "" [
    #text(font: font-heading, weight: "medium", size: 10.5pt, fill: lukb-blue)[#meta.subtitle]
    #v(4pt)
  ]

  #text(font: font-heading, weight: "medium", size: 20pt, fill: lukb-navy)[#meta.title]

  #if meta.lead != "" [
    #v(8pt)
    #text(font: font-body, weight: "light", size: 10.8pt, fill: lukb-text)[
      #eval(meta.lead_typst, mode: "markup")
    ]
  ]

  #if meta.authors.len() > 0 [
    #v(10pt)
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
  } else if blk.type == "figure" {
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
  }
}

#let render-balanced-col-run(items, gutter: 16pt) = context {
  let start-pos = here().position()
  layout(bounds => {
    let col-w = (bounds.width - gutter) / 2
    let page-h = 841.89pt
    let bottom-margin = 2.1cm
    let avail-h = page-h - start-pos.y - bottom-margin

    let item-heights = items.map(it => {
      let h = measure(block(width: col-w, render-single-block(it, in-box: false))).height
      if it.type == "heading" { h + 16pt } else { h + 8pt }
    })
    let total-h = item-heights.sum(default: 0pt)

    let best-split-h = total-h
    for split-idx in range(0, items.len() + 1) {
      let left-h = item-heights.slice(0, split-idx).sum(default: 0pt)
      let right-h = item-heights.slice(split-idx).sum(default: 0pt)
      let candidate = calc.max(left-h, right-h)
      if candidate < best-split-h {
        best-split-h = candidate
      }
    }

    let ideal-half = total-h / 2 + 20pt
    let target-h = if best-split-h <= ideal-half + 110pt {
      calc.max(ideal-half, best-split-h + 6pt)
    } else {
      ideal-half + 18pt
    }

    if avail-h > 100pt and target-h <= avail-h - 6pt {
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
  })
}

#{
  let runs = ()
  let curr-cols = ()
  for blk in blocks {
    let is-full = (blk.type in ("figure", "table")) and (blk.at("layout", default: "column") == "full")
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
