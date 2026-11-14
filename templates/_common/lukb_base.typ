// ============================================================================
// LUKB Gemeinsames Typst-Basismodul (`templates/_common/lukb_base.typ`)
// Zentrale Corporate-Design-Farben, Schriften, Kopf-/Fusszeilen,
// Inhaltsblock-Renderer sowie 2-Spalten- und Tufte-Layout-Algorithmen.
// ============================================================================

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

// A4 Seitengeometrie-Konstanten
#let page-w = 595.28pt
#let page-h = 841.89pt
#let page-top-margin = 2cm
#let page-bottom-margin = 2.4cm
#let page-side-margin = 1.5cm
#let page-content-w = page-w - 2 * page-side-margin
#let max-float-h = 520pt

// Tufte-Spaltenmasse (116mm + 8mm + 56mm = 180mm Satzspiegel auf A4 mit 2 x 15mm Rand)
#let tufte-main-w = 116mm
#let tufte-gutter = 8mm
#let tufte-margin-w = 56mm

// ============================================================================
// Hilfsfunktionen (Datum, Textbereinigung, Bildpfade)
// ============================================================================

#let format-pub-date(d) = {
  if d == none or d == "" { return "" }
  let s = str(d).trim()
  let months = ("", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember")
  let parts = s.split("-")
  if parts.len() == 3 {
    let y = parts.at(0)
    let m-str = parts.at(1)
    let d-part = parts.at(2).slice(0, calc.min(2, parts.at(2).len()))
    if m-str.matches(regex("^\d+$")).len() > 0 and d-part.matches(regex("^\d+$")).len() > 0 {
      let m = int(m-str)
      let day = int(d-part)
      if m >= 1 and m <= 12 {
        return str(day) + ". " + months.at(m) + " " + y
      }
    }
  }
  return s
}

#let clean-pub-title(raw-title) = {
  if raw-title == none { return "" }
  let s = str(raw-title).trim()
  if s.starts-with("\"") and s.ends-with("\"") and s.len() >= 2 {
    s = s.slice(1, s.len() - 1)
  }
  if s.starts-with("«") and s.ends-with("»") and s.len() >= 2 {
    s = s.slice(1, s.len() - 1)
  }
  return s
}

#let resolve-asset-path(p) = {
  if p == none or p == "" { return "" }
  let s = str(p).trim()
  if s.starts-with("/") { s } else { "/" + s }
}

// ============================================================================
// Überlappungsfreie Fusszeile (Seite 1 mit Disclaimer + Seitenzahl im Grid)
// ============================================================================

#let render-page-footer(meta, page-font-size: 9.5pt) = context {
  let page-num = counter(page).get().first()
  let total-pages = counter(page).final().first()
  let page-str = text(font: font-body, weight: "light", size: page-font-size, fill: lukb-muted)[#page-num/#total-pages]
  let disclaimer = str(meta.at("disclaimer", default: "")).trim()

  if page-num == 1 and disclaimer != "" {
    align(top)[
      #block(
        width: 100%,
        inset: (top: 5pt),
        stroke: (top: 0.5pt + black)
      )[
        #grid(
          columns: (1fr, auto),
          column-gutter: 12pt,
          align: (left + bottom, right + bottom),
          [
            #set par(justify: false, leading: 0.25em)
            #text(font: font-body, weight: "light", size: 6.8pt, fill: black)[#disclaimer]
          ],
          [#page-str]
        )
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

// ============================================================================
// Dokumenten-Kopf-Bausteine (Standard & Executive-Briefing)
// ============================================================================

#let render-brand-top-row(meta) = {
  grid(
    columns: (1fr, auto),
    align(left + top)[
      #image(resolve-asset-path("LUKB-Logo.svg"), height: 30pt)
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
}

#let render-tags-row(meta, top-space: 6pt, bottom-space: 0pt) = {
  let tags = meta.at("tags", default: ())
  if tags.len() > 0 [
    #if top-space > 0pt [ #v(top-space) ]
    #stack(
      dir: ltr,
      spacing: 5pt,
      ..tags.map(tag => box(
        fill: rgb("#F1F5F9"),
        stroke: 0.5pt + rgb("#CBD5E1"),
        radius: 2pt,
        inset: (x: 5pt, y: 2.5pt),
        outset: 0pt,
        baseline: 0%,
        [#text(font: font-heading, size: 7.5pt, weight: "medium", fill: lukb-navy)[#tag]]
      ))
    )
    #if bottom-space > 0pt [ #v(bottom-space) ]
  ]
}

#let render-standard-header(meta, title-below: 3em, lead-below: 3em) = {
  v(-0.75cm)
  block(
    width: 100%,
    inset: (bottom: 12pt),
    stroke: (bottom: 1.5pt + lukb-navy)
  )[
    #render-brand-top-row(meta)
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

    #block(above: 12pt, below: title-below)[
      #align(left)[
        #set par(justify: false, leading: 0.42em)
        #set text(hyphenate: false)
        #text(font: font-heading, weight: "medium", size: 22pt, fill: lukb-navy)[#meta.title]
      ]
    ]

    #if meta.lead != "" [
      #block(above: 0pt, below: lead-below)[
        #align(left)[
          #set par(justify: false, leading: 0.68em)
          #text(font: font-body, weight: "light", size: 10.8pt, fill: lukb-text)[#meta.lead]
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

    #render-tags-row(meta, top-space: 6pt, bottom-space: 0pt)
  ]
  v(8pt)
}

#let render-executive-header(meta) = {
  v(-0.75cm)
  render-brand-top-row(meta)
  v(12pt)

  block(
    width: 100%,
    fill: lukb-navy,
    inset: (x: 16pt, y: 14pt),
    radius: 3pt
  )[
    #grid(
      columns: (1fr, auto),
      align(left + horizon)[
        #text(font: font-heading, weight: "medium", size: 9pt, fill: lukb-cyan, tracking: 0.8pt)[
          LUKB INVESTMENT OFFICE · #upper(meta.at("category", default: ""))
        ]
      ],
      align(right + horizon)[
        #text(font: font-body, weight: "light", size: 10.5pt, fill: rgb("#D6DEE8"))[
          #format-pub-date(meta.publication_date)
        ]
      ]
    )
    #v(6pt)
    #if meta.subtitle != "" [
      #text(font: font-body, weight: "light", size: 10pt, fill: rgb("#B8C7D9"))[#meta.subtitle]
      #v(3pt)
    ]
    #align(left)[
      #set par(justify: false, leading: 0.42em)
      #set text(hyphenate: false)
      #text(font: font-heading, weight: "medium", size: 20.5pt, fill: white)[#meta.title]
    ]
  ]

  v(2.5em)

  if meta.lead != "" [
    #block(
      width: 100%,
      stroke: (left: 3pt + lukb-cyan),
      inset: (left: 12pt, y: 4pt)
    )[
      #align(left)[
        #set par(justify: false, leading: 0.68em)
        #text(font: font-heading, weight: "medium", size: 10.8pt, fill: lukb-navy)[#meta.lead]
      ]
    ]
    #v(2.5em)
  ]

  if meta.authors.len() > 0 [
    #text(font: font-body, weight: "light", size: 8.5pt, fill: lukb-muted)[
      Verfasst von:
      #for (idx, a) in meta.authors.enumerate() [
        #if idx > 0 [ · ]
        #text(font: font-heading, weight: "medium", fill: lukb-text)[#a.name]
        #if a.role != "" [ (#a.role) ]
      ]
    ]
    #v(6pt)
  ]

  render-tags-row(meta, top-space: 0pt, bottom-space: 6pt)
  line(length: 100%, stroke: 0.6pt + lukb-border)
  v(6pt)
}

// ============================================================================
// Gemeinsame Inhaltsblock-Komponenten
// ============================================================================

#let render-heading(
  level,
  content-text,
  h1-size: 14.5pt,
  h2-size: 10.8pt,
  h3-size: 9.8pt,
  above-space: 2.0em,
  h1-below: 6.5pt,
  below-space: 0.68em,
) = {
  let sz = if level == 1 { h1-size } else if level == 2 { h2-size } else { h3-size }
  let col = if level == 1 { lukb-navy } else if level == 2 { lukb-blue } else { lukb-text }
  let lead = if level == 1 { 0.42em } else if level == 2 { 0.38em } else { 0.34em }
  let blw = if level == 1 { h1-below } else { below-space }
  if level == 1 {
    block(
      width: 100%,
      sticky: true,
      breakable: false,
      above: above-space,
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
      above: above-space,
      below: blw
    )[
      #set text(hyphenate: false)
      #set par(leading: lead, justify: false)
      #text(font: font-heading, weight: "medium", size: sz, fill: col)[#content-text]
    ]
  }
}

#let render-callout(
  title,
  markup-str,
  accent-color: lukb-cyan,
  title-size: 10pt,
  body-size: 9pt,
) = {
  block(
    width: 100%,
    breakable: false,
    fill: lukb-surface,
    stroke: (left: 3pt + accent-color, top: 0.5pt + lukb-border, right: 0.5pt + lukb-border, bottom: 0.5pt + lukb-border),
    inset: (x: 11pt, y: 10pt),
    radius: (right: 3pt),
    above: 1em,
    below: 1.1em
  )[
    #if title != "" [
      #block(above: 0pt, below: 1.0em)[
        #text(font: font-heading, weight: "medium", size: title-size, fill: lukb-navy)[#title]
      ]
    ]
    #set text(size: body-size)
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

#let render-figure-box(blk, is-margin: false, allow-float: true) = {
  let is-floating = allow-float and (not is-margin) and (blk.at("layout", default: "column") == "full") and (not blk.at("_inline_full", default: false))
  let title-sz = if is-margin { 8.8pt } else { 10pt }
  let sub-sz = if is-margin { 7.6pt } else { 8.3pt }
  let src-sz = if is-margin { 6.8pt } else { 7.5pt }
  let img-path = resolve-asset-path(blk.at("resolved_image", default: ""))

  let fig-box = block(
    width: 100%,
    breakable: false,
    stroke: (top: 1.5pt + lukb-navy, bottom: 0.6pt + lukb-border),
    inset: (top: if is-margin { 6pt } else { 7pt }, bottom: if is-margin { 5pt } else { 6pt }),
    above: if is-floating { 0pt } else if is-margin { 0.4em } else { 2.0em },
    below: if is-floating { 0pt } else if is-margin { 0.6em } else { 1.1em }
  )[
    #if blk.title != "" [
      #block(sticky: true, breakable: false, above: 0pt, below: if blk.subtitle != "" { if is-margin { 4.5pt } else { 5.5pt } } else { if is-margin { 5pt } else { 6pt } })[
        #set par(leading: 0.28em, justify: false)
        #text(font: font-heading, weight: "medium", size: title-sz, fill: lukb-navy)[#blk.title]
      ]
    ]
    #if blk.subtitle != "" [
      #block(sticky: true, breakable: false, above: 0pt, below: if is-margin { 5pt } else { 6pt })[
        #set par(leading: 0.28em, justify: false)
        #text(font: font-body, weight: "light", size: sub-sz, fill: lukb-muted)[#blk.subtitle]
      ]
    ]
    #if img-path != "" [
      #align(center)[
        #image(img-path, width: 100%)
      ]
    ] else [
      #rect(
        width: 100%,
        height: if is-margin { 75pt } else { 95pt },
        fill: lukb-surface,
        stroke: (paint: lukb-border, dash: "dashed")
      )[
        #align(center + horizon)[
          #text(size: if is-margin { 7.5pt } else { 8.5pt }, fill: lukb-muted)[Grafik-Platzhalter (Bitte SVG oder PNG im Editor hochladen)]
        ]
      ]
    ]
    #if blk.source != "" [
      #v(2pt)
      #text(font: font-body, weight: "light", size: src-sz, fill: lukb-muted)[#blk.source]
    ]
  ]

  if is-floating {
    place-full-float(blk, fig-box)
  } else {
    fig-box
  }
}

#let render-table-box(blk, is-margin: false, allow-float: true, style-variant: "navy") = {
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

  let is-floating = allow-float and (not is-margin) and (blk.at("layout", default: "column") == "full") and (not blk.at("_inline_full", default: false))
  let has-source = (blk.source != "")
  let is-long-table = (rows.len() > 8)
  let can-break = is-long-table and (not is-floating) and (not is-margin)

  let title-sz = if is-margin { 8.8pt } else { 10pt }
  let sub-sz = if is-margin { 7.6pt } else { 8.3pt }
  let hdr-sz = if is-margin { 7.4pt } else { 8.2pt }
  let cell-sz = if is-margin { 7.4pt } else { 8.3pt }
  let pad-x = if is-margin { 3.5pt } else { 6pt }
  let pad-y = if is-margin { 3pt } else { 5pt }
  let is-tufte-style = (style-variant == "tufte")

  let tbl-box = block(
    width: 100%,
    breakable: can-break,
    above: if is-floating { 0pt } else if is-margin { 0.4em } else { 1.1em },
    below: if is-floating { 0pt } else if is-margin { 0.6em } else { 1.1em }
  )[
    #block(
      width: 100%,
      sticky: true,
      breakable: false,
      stroke: (top: 1.5pt + lukb-navy),
      inset: (top: if is-margin { 6pt } else { 7pt }),
      above: 0pt,
      below: if blk.title != "" or blk.subtitle != "" { if is-margin { 5pt } else { 6pt } } else { 2pt }
    )[
      #if blk.title != "" [
        #block(above: 0pt, below: if blk.subtitle != "" { if is-margin { 4pt } else { 5.5pt } } else { 0pt })[
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
    #let highlight-last = blk.at("highlight_last_row", default: false)
    #let main-rows-count = if is-long-table and has-source and rows.len() > 0 { rows.len() - 1 } else { rows.len() }

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
          if y == main-rows-count { 0.8pt + lukb-navy } else if is-tufte-style { none } else { 0.4pt + lukb-border }
        } else {
          if main-rows-count > 0 and y == main-rows-count - 1 { 0.8pt + lukb-navy } else if is-tufte-style { none } else { 0.4pt + lukb-border }
        },
        ..(if is-tufte-style { (left: none, right: none) } else { (:) })
      ),
      fill: (x, y) => {
        if show-header {
          if y == 0 { if is-tufte-style { lukb-surface } else { lukb-navy } }
          else if highlight-last and y == rows.len() { rgb("#E6EEF7") }
          else if calc.even(y) { if is-tufte-style { rgb("#FAFBFD") } else { lukb-surface } }
          else { white }
        } else {
          if rows.len() > 0 and highlight-last and y == rows.len() - 1 { rgb("#E6EEF7") }
          else if calc.odd(y) { if is-tufte-style { rgb("#FAFBFD") } else { lukb-surface } }
          else { white }
        }
      },
      inset: (x: pad-x, y: pad-y),
      ..(if show-header {
        (
          table.header(
            repeat: true,
            ..cols.map(c => text(
              font: font-heading,
              weight: "medium",
              size: hdr-sz,
              fill: if is-tufte-style { lukb-navy } else { white }
            )[#c.title]),
          ),
        )
      } else {
        ()
      }),
      ..for (r-idx, row-dict) in rows.slice(0, main-rows-count).enumerate() {
        let is-total = highlight-last and (r-idx == rows.len() - 1)
        cols.map(c => {
          let cell-val = row-dict.at(c.field, default: "")
          if is-total {
            text(font: font-heading, weight: "medium", size: cell-sz, fill: lukb-navy)[#cell-val]
          } else {
            text(font: font-body, weight: "light", size: cell-sz, fill: lukb-text)[#cell-val]
          }
        })
      },
      ..(if is-long-table and has-source and rows.len() > 0 {
        let last-idx = rows.len() - 1
        let last-row = rows.last()
        let is-total = highlight-last
        let last-bg = if is-total { rgb("#E6EEF7") } else if calc.even(last-idx + (if show-header { 1 } else { 0 })) { if is-tufte-style { rgb("#FAFBFD") } else { lukb-surface } } else { white }
        (
          table.cell(
            colspan: col-count,
            breakable: false,
            inset: 0pt,
            stroke: none,
            fill: none,
            [
              #grid(
                columns: col-widths,
                inset: (x: pad-x, y: pad-y),
                align: aligns,
                stroke: (x, y) => (
                  top: 0.4pt + lukb-border,
                  bottom: 0.8pt + lukb-navy,
                  ..(if is-tufte-style { (left: none, right: none) } else { (:) })
                ),
                fill: (x, y) => last-bg,
                ..cols.map(c => {
                  let cell-val = last-row.at(c.field, default: "")
                  if is-total {
                    text(font: font-heading, weight: "medium", size: cell-sz, fill: lukb-navy)[#cell-val]
                  } else {
                    text(font: font-body, weight: "light", size: cell-sz, fill: lukb-text)[#cell-val]
                  }
                })
              )
              #block(
                width: 100%,
                breakable: false,
                stroke: (bottom: 0.6pt + lukb-border),
                inset: (top: 4pt, bottom: if is-margin { 5pt } else { 6pt }),
                above: 0pt,
                below: 0pt
              )[
                #text(font: font-body, weight: "light", size: if is-margin { 6.8pt } else { 7.5pt }, fill: lukb-muted)[#blk.source]
              ]
            ]
          ),
        )
      } else {
        ()
      })
    )

    #if not (is-long-table and has-source and rows.len() > 0) [
      #block(
        width: 100%,
        breakable: false,
        stroke: (bottom: 0.6pt + lukb-border),
        inset: (top: if blk.source != "" { 4pt } else { 0pt }, bottom: if is-margin { 5pt } else { 6pt }),
        above: 0pt,
        below: 0pt
      )[
        #if blk.source != "" [
          #text(font: font-body, weight: "light", size: if is-margin { 6.8pt } else { 7.5pt }, fill: lukb-muted)[#blk.source]
        ]
      ]
    ]
  ]

  if is-floating {
    place-full-float(blk, tbl-box)
  } else {
    tbl-box
  }
}

#let render-quote-box(
  quote-text,
  author,
  source,
  accent-color: lukb-cyan,
  is-margin: false,
  tufte-style: false,
) = {
  let q-sz = if is-margin { 8.8pt } else { 10.2pt }
  block(
    width: 100%,
    breakable: false,
    stroke: (left: 3pt + accent-color),
    fill: if tufte-style { none } else { rgb("#F8FAFC") },
    inset: if tufte-style { (left: 9pt, top: 4pt, bottom: 4pt) } else { (left: 11pt, right: 8pt, y: 7pt) },
    radius: (right: 2pt),
    above: 1.1em,
    below: 1.1em
  )[
    #set par(leading: if tufte-style { 0.45em } else { 0.38em }, justify: false)
    #if tufte-style [
      #text(font: font-heading, weight: "medium", size: q-sz, fill: lukb-navy)[«#quote-text»]
    ] else [
      #text(font: font-heading, style: "italic", size: q-sz, fill: lukb-navy)[#quote-text]
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
  if style == "double" {
    block(
      width: 100%,
      above: 1.2em,
      below: 1.2em,
      stack(
        spacing: 2pt,
        line(length: 100%, stroke: 0.6pt + lukb-navy),
        line(length: 100%, stroke: 0.6pt + lukb-navy),
      )
    )
  } else {
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
}

#let render-footnotes-box(title, items) = {
  if items.len() == 0 { return }
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
        #set par(leading: 0.28em, justify: false)
        #if num != "" [
          #text(font: font-heading, weight: "medium", size: 7.5pt, fill: lukb-cyan)[\[#num\] ]
        ]
        #text(font: font-body, weight: "light", size: 7.5pt, fill: lukb-muted)[#txt]
      ]
    ]
  ]
}

#let render-glossary-box(title, items, two-columns: false) = {
  if items.len() == 0 { return }
  block(
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
    #if two-columns [
      #grid(
        columns: (1fr, 1fr),
        column-gutter: 14pt,
        row-gutter: 4pt,
        ..items.map(item => [
          #let term = item.at("term", default: "")
          #let def = item.at("definition", default: "")
          #set par(leading: 0.28em, justify: false)
          #text(font: font-heading, weight: "medium", size: 7.8pt, fill: lukb-navy)[#term]
          #h(3pt)
          #text(font: font-body, weight: "light", size: 7.6pt, fill: lukb-muted)[—]
          #h(3pt)
          #text(font: font-body, weight: "light", size: 7.6pt, fill: lukb-text)[#def]
        ])
      )
    ] else [
      #for item in items [
        #let term = item.at("term", default: "")
        #let def = item.at("definition", default: "")
        #block(above: 2.5pt, below: 2.5pt)[
          #set par(leading: 0.28em, justify: false)
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

#let render-publications-box(title, items, two-columns: false) = {
  let active-items = items.filter(it => it.at("enabled", default: true))
  if active-items.len() == 0 { return }

  let render-pub-entry(item) = {
    let clean-title = clean-pub-title(item.at("title", default: ""))
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
  }

  block(
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
    #if two-columns [
      #grid(
        columns: (1fr, 1fr),
        column-gutter: 14pt,
        row-gutter: 5pt,
        ..active-items.map(render-pub-entry)
      )
    ] else [
      #stack(
        spacing: 5pt,
        ..active-items.map(render-pub-entry)
      )
    ]
  ]
}

// ============================================================================
// Zweispaltiger Hauptteil mit O(N)-Spaltenausgleich (für investment_focus & market_flash)
// ============================================================================

#let render-single-block(
  blk,
  in-box: false,
  inline-full: false,
  callout-accent: lukb-cyan,
  quote-accent: lukb-cyan,
  heading-below: 0.68em,
) = {
  if blk.type == "heading" {
    render-heading(blk.level, blk.text, below-space: heading-below)
  } else if blk.type == "richtext" {
    eval(blk.typst_markup, mode: "markup")
    parbreak()
  } else if blk.type == "callout" {
    render-callout(blk.title, blk.typst_markup, accent-color: callout-accent)
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
          #render-single-block(
            child,
            in-box: true,
            callout-accent: callout-accent,
            quote-accent: quote-accent,
            heading-below: heading-below,
          )
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
      blk.at("source_typst", default: blk.at("source", default: "")),
      accent-color: quote-accent,
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

#let render-balanced-col-run(
  items,
  gutter: 16pt,
  callout-accent: lukb-cyan,
  quote-accent: lukb-cyan,
  heading-below: 0.68em,
) = context {
  let start-pos = here().position()
  let col-w = (page-content-w - gutter) / 2
  let avail-h = page-h - start-pos.y - page-bottom-margin
  let page-body-h = page-h - page-top-margin - page-bottom-margin

    let render-item(it) = render-single-block(
      it,
      in-box: false,
      callout-accent: callout-accent,
      quote-accent: quote-accent,
      heading-below: heading-below,
    )

    let has-full-float = items.any(it => (it.type in ("figure", "db_chart", "table")) and (it.at("layout", default: "column") == "full"))
    let manual-colbreak-idx = items.position(it => it.type == "colbreak")

    if has-full-float {
      columns(2, gutter: gutter)[
        #for it in items [ #render-item(it) ]
      ]
    } else if manual-colbreak-idx != none and avail-h > 100pt {
      let left-items = items.slice(0, manual-colbreak-idx)
      let right-items = items.slice(manual-colbreak-idx + 1)
      let left-h = measure(block(width: col-w, for it in left-items [ #render-item(it) ])).height
      let right-h = measure(block(width: col-w, for it in right-items [ #render-item(it) ])).height
      let max-h = calc.max(left-h, right-h)
      if max-h <= avail-h - 6pt {
        grid(
          columns: (1fr, 1fr),
          column-gutter: gutter,
          align: (top + left, top + left),
          [ #for it in left-items [ #render-item(it) ] ],
          [ #for it in right-items [ #render-item(it) ] ]
        )
      } else {
        columns(2, gutter: gutter)[
          #for it in items [ #render-item(it) ]
        ]
      }
    } else {
      // O(N) Spaltenausgleich: Jeder Block wird exakt einmal vermessen,
      // danach wird über Präfixsummen der beste Trennpunkt bestimmt.
      let best-split-idx = 0
      let best-diff = 999999pt
      let best-max-h = 999999pt

      if items.len() >= 2 {
        let item-heights = items.map(it => measure(block(width: col-w, render-item(it))).height)
        let inter-gap = 12pt
        let prefix-h = (0pt,)
        let running = 0pt
        for (idx, h) in item-heights.enumerate() {
          running = running + h + (if idx > 0 { inter-gap } else { 0pt })
          prefix-h.push(running)
        }
        let total-est = prefix-h.last()

        let best-score = 999999pt
        for split-idx in range(1, items.len()) {
          let prev-is-heading = (items.at(split-idx - 1).type == "heading")
          if not prev-is-heading {
            let left-est = prefix-h.at(split-idx)
            let right-est = calc.max(0pt, total-est - left-est - inter-gap)
            let diff = calc.abs(left-est - right-est)
            let right-heavy-penalty = if right-est > left-est + 2pt { 60pt } else { 0pt }
            let score = diff + right-heavy-penalty
            if score < best-score {
              best-score = score
              best-split-idx = split-idx
            }
          }
        }

        if best-split-idx > 0 {
          let left-items = items.slice(0, best-split-idx)
          let right-items = items.slice(best-split-idx)
          let left-h = measure(block(width: col-w, for it in left-items [ #render-item(it) ])).height
          let right-h = measure(block(width: col-w, for it in right-items [ #render-item(it) ])).height
          best-diff = calc.abs(left-h - right-h)
          best-max-h = calc.max(left-h, right-h)
        }
      }

      // Nutze den Block-Split nur dann, wenn die Spalten dadurch harmonisch ausbalanciert sind
      // (Differenz <= 90pt) und auf die Seite passen. Andernfalls fliesst der Text über echtes #columns(2).
      let fits-current-or-next = (avail-h > 80pt and best-max-h <= (avail-h + 10pt)) or (avail-h <= 80pt and best-max-h <= page-body-h)
      if best-split-idx > 0 and best-diff <= 90pt and fits-current-or-next {
        if avail-h <= 80pt {
          pagebreak(weak: true)
        }
        let left-items = items.slice(0, best-split-idx)
        let right-items = items.slice(best-split-idx)
        grid(
          columns: (1fr, 1fr),
          column-gutter: gutter,
          align: (top + left, top + left),
          [ #for it in left-items [ #render-item(it) ] ],
          [ #for it in right-items [ #render-item(it) ] ]
        )
      } else {
        let has-table = items.any(it => it.type == "table")
        let total-h = measure(block(width: col-w, for it in items [ #render-item(it) ])).height
        let ideal-half = total-h / 2 + 16pt
        let target-h = if best-max-h < 900000pt { calc.max(ideal-half, best-max-h + 6pt) } else { ideal-half }

        if not has-table and avail-h > 100pt and target-h <= (avail-h - 6pt) {
          block(
            width: 100%,
            height: target-h,
            columns(2, gutter: gutter)[
              #for it in items [ #render-item(it) ]
            ]
          )
        } else {
          columns(2, gutter: gutter)[
            #for it in items [ #render-item(it) ]
          ]
        }
      }
    }
}

#let render-col-run-smart(
  items,
  bounds,
  max-float-h: max-float-h,
  gutter: 16pt,
  callout-accent: lukb-cyan,
  quote-accent: lukb-cyan,
  heading-below: 0.68em,
) = context {
  let start-pos = here().position()
  let col-w = (bounds.width - gutter) / 2
  let page-body-h = page-h - page-top-margin - page-bottom-margin
  let avail-h = calc.max(0pt, page-h - start-pos.y - page-bottom-margin)

  let has-full-table = items.any(it => it.type == "table" and it.at("layout", default: "column") == "full")
  if not has-full-table {
    render-balanced-col-run(
      items,
      gutter: gutter,
      callout-accent: callout-accent,
      quote-accent: quote-accent,
      heading-below: heading-below,
    )
  } else {
    let used-h = 0pt
    let pending-sum-h = 0pt
    let pending-max-indiv-h = 0pt
    let overflow-idx = none

    for (idx, it) in items.enumerate() {
      let is-full = (it.type in ("figure", "db_chart", "table")) and (it.at("layout", default: "column") == "full")
      if not is-full {
        let ih = measure(block(
          width: col-w,
          render-single-block(
            it,
            in-box: false,
            callout-accent: callout-accent,
            quote-accent: quote-accent,
            heading-below: heading-below,
          )
        )).height
        pending-sum-h = pending-sum-h + ih + 8pt
        if it.type in ("figure", "db_chart", "callout", "quote") and ih > pending-max-indiv-h {
          pending-max-indiv-h = ih
        }
      } else {
        if pending-sum-h > 0pt {
          used-h = used-h + calc.max(pending-sum-h / 2 + 8pt, pending-max-indiv-h + 8pt)
          pending-sum-h = 0pt
          pending-max-indiv-h = 0pt
        }

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
      render-balanced-col-run(
        items,
        gutter: gutter,
        callout-accent: callout-accent,
        quote-accent: quote-accent,
        heading-below: heading-below,
      )
    } else {
      if overflow-idx > 0 {
        render-balanced-col-run(
          items.slice(0, overflow-idx),
          gutter: gutter,
          callout-accent: callout-accent,
          quote-accent: quote-accent,
          heading-below: heading-below,
        )
      }
      render-single-block(
        items.at(overflow-idx),
        in-box: false,
        inline-full: true,
        callout-accent: callout-accent,
        quote-accent: quote-accent,
        heading-below: heading-below,
      )
      if overflow-idx + 1 < items.len() {
        render-col-run-smart(
          items.slice(overflow-idx + 1),
          bounds,
          max-float-h: max-float-h,
          gutter: gutter,
          callout-accent: callout-accent,
          quote-accent: quote-accent,
          heading-below: heading-below,
        )
      }
    }
  }
}

#let render-two-column-body(
  blocks,
  gutter: 16pt,
  callout-accent: lukb-cyan,
  quote-accent: lukb-cyan,
  heading-below: 0.68em,
) = context {
  let bounds = (width: page-content-w)
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
        render-single-block(
          run.item,
          in-box: false,
          inline-full: true,
          callout-accent: callout-accent,
          quote-accent: quote-accent,
          heading-below: heading-below,
        )
      } else {
        render-col-run-smart(
          run.items,
          bounds,
          max-float-h: max-float-h,
          gutter: gutter,
          callout-accent: callout-accent,
          quote-accent: quote-accent,
          heading-below: heading-below,
        )
      }
    }
}

// ============================================================================
// Asymmetrischer Tufte-Hauptteil mit entkoppelter Randspalten-Höhenlogik
// ============================================================================

#let render-tufte-single-block(blk, is-margin: false, build-rows-fn: none) = {
  if blk.type == "heading" {
    render-heading(
      blk.level,
      blk.text,
      h1-size: 13.5pt,
      h2-size: 10.5pt,
      h3-size: 9.6pt,
      above-space: 1.8em,
      h1-below: 6pt,
      below-space: 0.65em,
    )
  } else if blk.type == "richtext" {
    eval(blk.typst_markup, mode: "markup")
    parbreak()
  } else if blk.type == "callout" {
    render-callout(blk.title, blk.typst_markup, accent-color: lukb-cyan, title-size: 9.5pt, body-size: 8.8pt)
  } else if blk.type in ("figure", "db_chart") {
    render-figure-box(blk, is-margin: is-margin, allow-float: false)
  } else if blk.type == "table" {
    render-table-box(blk, is-margin: is-margin, allow-float: false, style-variant: "tufte")
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
      #if is-split and build-rows-fn != none [
        #let box-rows = build-rows-fn(blk.children, main-w: tufte-main-w - 10pt, margin-w: tufte-margin-w - 10pt)
        #grid(
          columns: (1fr, tufte-margin-w),
          column-gutter: tufte-gutter,
          row-gutter: 1.4em,
          ..box-rows.map(r => (
            [
              #for l-it in r.left [
                #render-tufte-single-block(l-it, is-margin: false, build-rows-fn: build-rows-fn)
              ]
            ],
            [
              #if r.right.len() > 0 [
                #stack(
                  spacing: 8pt,
                  ..r.right.map(r-it => render-tufte-single-block(r-it, is-margin: true, build-rows-fn: build-rows-fn))
                )
              ]
            ]
          )).flatten()
        )
      ] else [
        #for child in blk.children [
          #render-tufte-single-block(child, is-margin: is-margin, build-rows-fn: build-rows-fn)
        ]
      ]
    ]
  } else if blk.type == "spacer" {
    let h-mm = blk.at("height_mm", default: 8)
    v(h-mm * 1mm)
  } else if blk.type == "colbreak" {
    // Wird auf Run-Ebene als Seitenumbruch behandelt
  } else if blk.type == "quote" {
    render-quote-box(
      blk.at("quote_typst", default: blk.at("quote", default: "")),
      blk.at("author_typst", default: blk.at("author", default: "")),
      blk.at("source_typst", default: blk.at("source", default: "")),
      accent-color: lukb-gold,
      is-margin: is-margin,
      tufte-style: true,
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
      blk.at("items_typst", default: blk.at("items", default: ())),
      two-columns: true,
    )
  } else if blk.type == "publications" {
    render-publications-box(
      blk.at("title_typst", default: blk.at("title", default: "Weitere Publikationen")),
      blk.at("items_typst", default: blk.at("items", default: ())),
      two-columns: true,
    )
  }
}

// Höhenbewusste Tufte-Zeilenbildung:
// Verhindert weisse Lücken im linken Haupttext, wenn eine Randgrafik/-tabelle
// höher ist als ein einzelner Textabsatz. Aufeinanderfolgende Textabsätze fliessen
// links nahtlos weiter, bis die Höhe der rechten Randspalte erreicht ist.
#let build-tufte-grid-rows(items, main-w: tufte-main-w, margin-w: tufte-margin-w) = {
  let rows = ()
  let curr-left = ()
  let curr-right = ()
  let left-h = 0pt
  let right-h = 0pt

  let measure-main(blk) = measure(
    block(width: main-w, render-tufte-single-block(blk, is-margin: false, build-rows-fn: none))
  ).height + 10pt

  let measure-margin(blk) = measure(
    block(width: margin-w, render-tufte-single-block(blk, is-margin: true, build-rows-fn: none))
  ).height + 10pt

  for it in items {
    let is-margin = (it.type in ("figure", "db_chart", "table")) and (it.at("layout", default: "column") == "column")
    if is-margin {
      let mh = measure-margin(it)
      if curr-right.len() == 0 {
        // Erstes Rand-Element in dieser Zeile:
        // Falls links bereits mehrere Absätze stehen, spalten wir die älteren Absätze
        // als eigene Zeile ab und behalten den aktuellen Anker-Absatz (inkl. evtl. Überschrift davor),
        // damit das Rand-Element direkt neben seinem Anker-Absatz beginnt.
        let non-heading-count = curr-left.filter(x => x.type != "heading").len()
        if non-heading-count >= 2 {
          let split-at = curr-left.len() - 1
          if split-at >= 1 and curr-left.at(split-at - 1).type == "heading" {
            split-at = split-at - 1
          }
          if split-at > 0 {
            let flushed-left = curr-left.slice(0, split-at)
            let anchor-left = curr-left.slice(split-at)
            rows.push((left: flushed-left, right: ()))
            curr-left = anchor-left
            left-h = anchor-left.map(measure-main).fold(0pt, (a, b) => a + b)
          }
        }
        curr-right.push(it)
        right-h = mh
      } else if left-h > right-h + 12pt {
        // Die linke Hauptspalte ist bereits über das bisherige Rand-Element hinausgewachsen:
        // Wir können die Zeile ohne weisse Lücke abschliessen und das neue Rand-Element
        // auf Höhe des letzten/nächsten Absatzes verankern.
        let split-at = curr-left.len()
        if curr-left.len() >= 2 {
          let last-h = measure-main(curr-left.last())
          if (left-h - last-h) >= right-h {
            split-at = curr-left.len() - 1
            if split-at >= 1 and curr-left.at(split-at - 1).type == "heading" and (left-h - last-h - measure-main(curr-left.at(split-at - 1))) >= right-h {
              split-at = split-at - 1
            }
          }
        }
        let flushed-left = curr-left.slice(0, split-at)
        let anchor-left = curr-left.slice(split-at)
        rows.push((left: flushed-left, right: curr-right))
        curr-left = anchor-left
        left-h = anchor-left.map(measure-main).fold(0pt, (a, b) => a + b)
        curr-right = (it,)
        right-h = mh
      } else {
        // Die rechte Randspalte ist noch höher als der linke Text:
        // Kein neuer Grid-Zeilenumbruch (würde links ein weisses Loch reissen!),
        // sondern Rand-Element rechts darunter stapeln und Text links weiterfliessen lassen.
        curr-right.push(it)
        right-h = right-h + mh
      }
    } else {
      curr-left.push(it)
      left-h = left-h + measure-main(it)
    }
  }

  if curr-left.len() > 0 or curr-right.len() > 0 {
    rows.push((left: curr-left, right: curr-right))
  }
  return rows
}

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

#let render-tufte-body(blocks) = {
  let runs = build-tufte-runs(blocks)
  for run in runs {
    if run.kind == "break" {
      pagebreak(weak: true)
    } else if run.kind == "full" {
      context [
        #block(width: 100%)[
          #render-tufte-single-block(run.item, is-margin: false, build-rows-fn: build-tufte-grid-rows)
        ]
      ]
    } else {
      context {
        let rows = build-tufte-grid-rows(run.items, main-w: tufte-main-w, margin-w: tufte-margin-w)
        let gutters = if rows.len() > 1 {
          rows.slice(1).map(r => {
            if r.left.len() > 0 {
              let first-it = r.left.at(0)
              if first-it.type == "heading" {
                let lvl = first-it.at("level", default: 2)
                if lvl == 1 { 2.3em } else { 2.0em }
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
                #render-tufte-single-block(l-it, is-margin: false, build-rows-fn: build-tufte-grid-rows)
              ]
            ],
            [
              #if r.right.len() > 0 [
                #stack(
                  spacing: 10pt,
                  ..r.right.map(r-it => render-tufte-single-block(r-it, is-margin: true, build-rows-fn: build-tufte-grid-rows))
                )
              ]
            ]
          )).flatten()
        )
      }
    }
  }
}
