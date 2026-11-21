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

// Interaktive Vorschau-Links für PDF -> Editor-Fokus-Synchronisation
#let _cms-interactive-links = {
  let raw = sys.inputs.at("article_json", default: none)
  if raw == none { false } else { json(bytes(raw)).at("interactive_links", default: false) == true }
}

#let cms-link-block(blk, body) = {
  if not _cms-interactive-links { return body }
  let bid = str(blk.at("id", default: "")).trim()
  if bid == "" { return body }
  link("https://cms-block.invalid/block/" + bid, body)
}

#let cms-link-meta(field-id, body) = {
  if not _cms-interactive-links { return body }
  let fid = str(field-id).trim()
  if fid == "" { return body }
  link("https://cms-block.invalid/meta/" + fid, body)
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
            #cms-link-meta("meta-disclaimer")[
              #text(font: font-body, weight: "light", size: 6.8pt, fill: black)[#disclaimer]
            ]
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
        #cms-link-meta("meta-header-series")[
          #text(font: font-heading, weight: "medium", size: 14pt, fill: rgb("#0093D1"))[
            #header-series-text
          ]
        ]
      ]
    ]
  )
}

#let render-tags-row(meta, top-space: 6pt, bottom-space: 0pt) = {
  let tags = meta.at("tags", default: ())
  if tags.len() > 0 [
    #if top-space > 0pt [ #v(top-space) ]
    #cms-link-meta("meta-tags-container")[
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
    ]
    #if bottom-space > 0pt [ #v(bottom-space) ]
  ]
}

#let render-standard-header(meta, title-below: 2.2em, lead-below: 2.2em) = {
  v(-0.75cm)
  block(
    width: 100%,
    inset: (bottom: 12pt),
    stroke: (bottom: 1.5pt + lukb-navy)
  )[
    #render-brand-top-row(meta)
    #v(14pt)

    #let sub-line = if meta.subtitle != "" { meta.subtitle } else if meta.at("category", default: "") != "" { meta.category } else { "" }
    #let sub-field-id = if meta.subtitle != "" { "meta-subtitle" } else { "meta-category" }
    #let display-date = format-pub-date(meta.publication_date)

    #if sub-line != "" or display-date != "" [
      #grid(
        columns: (1fr, auto),
        gutter: 10pt,
        align(left + bottom)[
          #if sub-line != "" [
            #cms-link-meta(sub-field-id)[
              #text(font: font-heading, weight: "medium", size: 10.5pt, fill: lukb-blue)[#sub-line]
            ]
          ]
        ],
        align(right + bottom)[
          #if display-date != "" [
            #cms-link-meta("meta-pub-date")[
              #text(font: font-body, weight: "light", size: 11pt, fill: lukb-muted)[#display-date]
            ]
          ]
        ]
      )
      #v(4pt)
    ]

    #block(above: 12pt, below: title-below)[
      #align(left)[
        #set par(justify: false, leading: 0.42em)
        #set text(hyphenate: false)
        #cms-link-meta("meta-title")[
          #text(font: font-heading, weight: "medium", size: 22pt, fill: lukb-navy)[#meta.title]
        ]
      ]
    ]

    #if meta.lead != "" [
      #block(above: 0pt, below: lead-below)[
        #align(left)[
          #set par(justify: false, leading: 0.68em)
          #cms-link-meta("meta-lead")[
            #text(font: font-body, weight: "light", size: 10.8pt, fill: lukb-text)[#meta.lead]
          ]
        ]
      ]
    ]

    #if meta.authors.len() > 0 [
      #cms-link-meta("meta-authors-container")[
        #block(
          width: 100%,
          fill: lukb-surface,
          inset: (x: 10pt, y: 6pt),
          radius: 2pt
        )[
          #text(font: font-heading, weight: "medium", size: 8pt, fill: lukb-navy)[Verfasst von: ]
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
        #let cat-text = meta.at("category", default: "")
        #cms-link-meta("meta-category")[
          #text(font: font-heading, weight: "medium", size: 9pt, fill: lukb-cyan, tracking: 0.8pt)[
            #if cat-text != "" [LUKB INVESTMENT OFFICE · #upper(cat-text)] else [LUKB INVESTMENT OFFICE]
          ]
        ]
      ],
      align(right + horizon)[
        #cms-link-meta("meta-pub-date")[
          #text(font: font-body, weight: "light", size: 10.5pt, fill: rgb("#D6DEE8"))[
            #format-pub-date(meta.publication_date)
          ]
        ]
      ]
    )
    #v(6pt)
    #if meta.subtitle != "" [
      #cms-link-meta("meta-subtitle")[
        #text(font: font-body, weight: "light", size: 10pt, fill: rgb("#B8C7D9"))[#meta.subtitle]
      ]
      #v(3pt)
    ]
    #align(left)[
      #set par(justify: false, leading: 0.42em)
      #set text(hyphenate: false)
      #cms-link-meta("meta-title")[
        #text(font: font-heading, weight: "medium", size: 20.5pt, fill: white)[#meta.title]
      ]
    ]
  ]

  v(2.5em)

  if meta.lead != "" [
    #cms-link-meta("meta-lead")[
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
    ]
    #v(2.5em)
  ]

  if meta.authors.len() > 0 [
    #cms-link-meta("meta-authors-container")[
      #text(font: font-body, weight: "light", size: 8.5pt, fill: lukb-muted)[
        Verfasst von:
        #for (idx, a) in meta.authors.enumerate() [
          #if idx > 0 [ · ]
          #text(font: font-heading, weight: "medium", fill: lukb-text)[#a.name]
          #if a.role != "" [ (#a.role) ]
        ]
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
  outline-level: none,
  h1-size: 14.5pt,
  h2-size: 10.8pt,
  h3-size: 9.8pt,
  above-space: 2.0em,
  h1-below: 6.5pt,
  below-space: 0.68em,
) = {
  let eff-outline-level = if outline-level != none { outline-level } else { level }
  let sz = if level == 1 { h1-size } else if level == 2 { h2-size } else { h3-size }
  let col = if level == 1 { lukb-navy } else if level == 2 { lukb-blue } else { lukb-text }
  let lead = if level == 1 { 0.42em } else if level == 2 { 0.38em } else { 0.34em }
  let blw = if level == 1 { h1-below } else { below-space }
  let clean-title = str(content-text).trim()
  let do-outline = clean-title != ""
  if level == 1 {
    block(
      width: 100%,
      sticky: true,
      breakable: false,
      above: above-space,
      below: blw
    )[
      #show heading: it => it.body
      #stack(
        spacing: 4.5pt,
        block(width: 100%)[
          #set text(hyphenate: false)
          #set par(leading: lead, justify: false)
          #heading(level: eff-outline-level, outlined: do-outline)[#text(font: font-heading, weight: "medium", size: sz, fill: col)[#content-text]]
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
      #show heading: it => it.body
      #set text(hyphenate: false)
      #set par(leading: lead, justify: false)
      #heading(level: eff-outline-level, outlined: do-outline)[#text(font: font-heading, weight: "medium", size: sz, fill: col)[#content-text]]
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
    #if markup-str != none and markup-str.trim() != "" [
      #eval(markup-str, mode: "markup")
    ]
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

#let render-box-title-subtitle(
  title,
  subtitle,
  title-sz,
  sub-sz,
  is-margin: false,
  title-below-with-sub: auto,
  title-below-no-sub: 0pt,
  sub-below: 0pt,
  sticky-blocks: false,
) = {
  let eff-title-below-sub = if title-below-with-sub == auto { if is-margin { 4.5pt } else { 5.5pt } } else { title-below-with-sub }
  if title != "" [
    #block(sticky: sticky-blocks, breakable: false, above: 0pt, below: if subtitle != "" { eff-title-below-sub } else { title-below-no-sub })[
      #set par(leading: 0.28em, justify: false)
      #text(font: font-heading, weight: "medium", size: title-sz, fill: lukb-navy)[#title]
    ]
  ]
  if subtitle != "" [
    #block(sticky: sticky-blocks, breakable: false, above: 0pt, below: sub-below)[
      #set par(leading: 0.28em, justify: false)
      #text(font: font-body, weight: "light", size: sub-sz, fill: lukb-muted)[#subtitle]
    ]
  ]
}

#let render-box-source(source, is-margin: false, with-border: false, empty-bottom: false) = {
  let top-pad = if source != "" { if is-margin { 0.5em } else { 0.55em } } else { 0pt }
  let bot-pad = if is-margin { 5pt } else { 6pt }
  if with-border {
    block(
      width: 100%,
      breakable: false,
      stroke: (bottom: 0.6pt + lukb-border),
      inset: (top: top-pad, bottom: bot-pad),
      above: 0pt,
      below: 0pt,
    )[
      #if source != "" [
        #text(font: font-body, weight: "light", size: if is-margin { 6.8pt } else { 7.5pt }, fill: lukb-muted)[#source]
      ]
    ]
  } else if source != "" [
    #block(width: 100%, breakable: false, above: top-pad, below: 0pt)[
      #text(font: font-body, weight: "light", size: if is-margin { 6.8pt } else { 7.5pt }, fill: lukb-muted)[#source]
    ]
  ]
}

#let render-figure-box(blk, is-margin: false, allow-float: true) = {
  let is-floating = allow-float and (not is-margin) and (blk.at("layout", default: "column") == "full") and (not blk.at("_inline_full", default: false))
  let title-sz = if is-margin { 8.8pt } else { 10pt }
  let sub-sz = if is-margin { 7.6pt } else { 8.3pt }
  let img-path = resolve-asset-path(blk.at("resolved_image", default: ""))

  let fig-box = block(
    width: 100%,
    breakable: false,
    stroke: (top: 1.5pt + lukb-navy, bottom: 0.6pt + lukb-border),
    inset: (top: if is-margin { 6pt } else { 7pt }, bottom: if is-margin { 5pt } else { 6pt }),
    above: if is-floating { 0pt } else if is-margin { 0.4em } else { 2.0em },
    below: if is-floating { 0pt } else if is-margin { 0.6em } else { 1.1em }
  )[
    #render-box-title-subtitle(
      blk.title,
      blk.subtitle,
      title-sz,
      sub-sz,
      is-margin: is-margin,
      title-below-no-sub: if is-margin { 5pt } else { 6pt },
      sub-below: if is-margin { 5pt } else { 6pt },
      sticky-blocks: true,
    )
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
    #render-box-source(blk.source, is-margin: is-margin)
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

  let is-factsheet = (style-variant == "factsheet")
  let raw-font-step = int(blk.at("font_size_step", default: 0))
  let font-step = if raw-font-step <= -2 { -2 } else if raw-font-step >= 0 { 0 } else { -1 }
  let font-delta-pt = font-step * 0.7
  let title-sz = if is-factsheet { 8.5pt } else if is-margin { 8.8pt } else { 10pt }
  let sub-sz = if is-factsheet { 7.2pt } else if is-margin { 7.6pt } else { 8.3pt }
  let hdr-sz = calc.max(5.0, (if is-factsheet { 7.2 } else if is-margin { 7.4 } else { 8.2 }) + font-delta-pt) * 1pt
  let cell-sz = calc.max(5.0, (if is-factsheet { 7.0 } else if is-margin { 7.4 } else { 8.3 }) + font-delta-pt) * 1pt
  let pad-x = if is-factsheet { 3pt } else if is-margin { 3.5pt } else { 6pt }
  let pad-y = if is-factsheet { 1.8pt } else if is-margin { 3pt } else { 5pt }
  let is-tufte-style = (style-variant == "tufte")

  let tbl-box = block(
    width: 100%,
    breakable: can-break,
    above: if is-floating { 0pt } else if is-factsheet { 0.35em } else if is-margin { 0.4em } else { 1.1em },
    below: if is-floating { 0pt } else if is-factsheet { 0.45em } else if is-margin { 0.6em } else { 1.1em }
  )[
    #set par(justify: false)
    #block(
      width: 100%,
      sticky: true,
      breakable: false,
      stroke: (top: if is-factsheet { 1.2pt + lukb-navy } else { 1.5pt + lukb-navy }),
      inset: (top: if is-factsheet { 4pt } else if is-margin { 6pt } else { 7pt }),
      above: 0pt,
      below: if blk.title != "" or blk.subtitle != "" { if is-factsheet { 3pt } else if is-margin { 5pt } else { 6pt } } else { 2pt }
    )[
      #render-box-title-subtitle(
        blk.title,
        blk.subtitle,
        title-sz,
        sub-sz,
        is-margin: is-margin,
        title-below-with-sub: if is-margin { 4pt } else { 5.5pt },
      )
    ]

    #set table.cell(breakable: false)
    #let show-header = blk.at("show_header", default: true)
    #let highlight-last = blk.at("highlight_last_row", default: false)
    #let main-rows-count = if is-long-table and has-source and rows.len() > 0 { rows.len() - 1 } else { rows.len() }
    #let render-row-cells(row-dict, is-total) = cols.map(c => {
      let cell-val = row-dict.at(c.field, default: "")
      let cell-justify = (c.align == "justify")
      [
        #set par(justify: cell-justify)
        #(if is-total {
          text(font: font-heading, weight: "medium", size: cell-sz, fill: lukb-navy)[#cell-val]
        } else {
          text(font: font-body, weight: "light", size: cell-sz, fill: lukb-text)[#cell-val]
        })
      ]
    })

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
            ..cols.map(c => [
              #set par(justify: false)
              #text(
                font: font-heading,
                weight: "medium",
                size: hdr-sz,
                fill: if is-tufte-style { lukb-navy } else { white }
              )[#c.title]
            ]),
          ),
        )
      } else {
        ()
      }),
      ..for (r-idx, row-dict) in rows.slice(0, main-rows-count).enumerate() {
        let is-total = highlight-last and (r-idx == rows.len() - 1)
        render-row-cells(row-dict, is-total)
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
                ..render-row-cells(last-row, is-total)
              )
              #render-box-source(blk.source, is-margin: is-margin, with-border: true)
            ]
          ),
        )
      } else {
        ()
      })
    )

    #if not (is-long-table and has-source and rows.len() > 0) [
      #render-box-source(blk.source, is-margin: is-margin, with-border: true)
    ]
  ]

  if is-floating {
    place-full-float(blk, tbl-box)
  } else {
    tbl-box
  }
}

#let render-media-text-media(media-blk, is-compact: false) = {
  let mtype = media-blk.at("type", default: "figure")
  if mtype == "table" {
    let bcopy = media-blk
    bcopy.insert("_inline_full", true)
    render-table-box(bcopy, is-margin: is-compact, allow-float: false)
  } else {
    let img-path = resolve-asset-path(media-blk.at("resolved_image", default: ""))
    let has-meta = (str(media-blk.at("title", default: "")).trim() != "") or (str(media-blk.at("subtitle", default: "")).trim() != "") or (str(media-blk.at("source", default: "")).trim() != "")
    if has-meta {
      let bcopy = media-blk
      bcopy.insert("_inline_full", true)
      render-figure-box(bcopy, is-margin: is-compact, allow-float: false)
    } else if img-path != "" {
      image(img-path, width: 100%)
    } else {
      rect(
        width: 100%,
        height: 60pt,
        fill: lukb-surface,
        stroke: (paint: lukb-border, dash: "dashed")
      )[
        #align(center + horizon)[
          #text(size: 7.5pt, fill: lukb-muted)[Grafik-Platzhalter]
        ]
      ]
    }
  }
}

#let render-media-text-box(blk, is-margin: false, allow-float: true) = {
  let is-floating = allow-float and (not is-margin) and (blk.at("layout", default: "full") == "full") and (not blk.at("_inline_full", default: false))
  let style-preset = blk.at("style_preset", default: "plain")
  let is-zebra = (style-preset == "zebra")
  let is-card = (style-preset == "card")
  let zebra-idx = blk.at("_zebra_index", default: 0)
  let zebra-last = blk.at("_zebra_last", default: true)

  let fill-col = if is-zebra {
    if calc.even(zebra-idx) { lukb-surface } else { white }
  } else if is-card {
    white
  } else {
    none
  }
  let box-stroke = if is-card {
    0.6pt + lukb-border
  } else if is-zebra {
    (top: 0.4pt + rgb("#E6ECF2"), bottom: 0.4pt + rgb("#E6ECF2"))
  } else {
    none
  }
  let box-inset = if is-zebra {
    (x: 10pt, y: 9pt)
  } else if is-card {
    (x: 11pt, y: 10pt)
  } else {
    (x: 0pt, y: 3pt)
  }
  let box-above = if is-floating {
    0pt
  } else if is-zebra {
    if zebra-idx == 0 { 0.9em } else { 0pt }
  } else {
    1.0em
  }
  let box-below = if is-floating {
    0pt
  } else if is-zebra {
    if zebra-last { 0.9em } else { 0pt }
  } else {
    1.0em
  }

  let title-txt = str(blk.at("title_typst", default: blk.at("title", default: ""))).trim()
  let text-markup = str(blk.at("typst_markup", default: "")).trim()
  let aside-markup = str(blk.at("aside_typst_markup", default: "")).trim()
  let has-aside = aside-markup != ""
  let raw-pos = blk.at("media_position", default: "auto")
  let media-pct = float(blk.at("media_width_pct", default: 30))
  let aside-pct = float(blk.at("aside_width_pct", default: 26))
  let media-blk = blk.at("media", default: (:))

  let box-el = block(
    width: 100%,
    breakable: false,
    fill: fill-col,
    stroke: box-stroke,
    radius: if is-card { 3pt } else { 0pt },
    inset: box-inset,
    above: box-above,
    below: box-below,
  )[
    #if title-txt != "" [
      #block(above: 0pt, below: 6pt)[
        #text(font: font-heading, weight: "medium", size: 10pt, fill: lukb-navy)[#title-txt]
      ]
    ]
    #layout(bounds => {
      let eff-pos = if raw-pos == "auto" {
        if bounds.width >= 360pt { "left" } else { "top" }
      } else {
        raw-pos
      }
      let is-compact = bounds.width < 360pt
      let media-el = render-media-text-media(media-blk, is-compact: is-compact)
      let text-el = [
        #set par(justify: false, leading: 0.48em, spacing: 0.65em)
        #if text-markup != "" [
          #eval(text-markup, mode: "markup")
        ]
      ]
      let aside-el = if has-aside {
        [
          #set par(justify: false, leading: 0.42em, spacing: 0.55em)
          #set text(size: 8.6pt, fill: lukb-text)
          #eval(aside-markup, mode: "markup")
        ]
      } else {
        none
      }

      if eff-pos == "left" or eff-pos == "right" {
        let text-pct = if has-aside { calc.max(20.0, 100.0 - media-pct - aside-pct) } else { calc.max(20.0, 100.0 - media-pct) }
        if eff-pos == "left" {
          if has-aside {
            grid(
              columns: (media-pct * 1fr, text-pct * 1fr, aside-pct * 1fr),
              column-gutter: 14pt,
              align: (top + left, top + left, top + left),
              media-el, text-el, aside-el,
            )
          } else {
            grid(
              columns: (media-pct * 1fr, text-pct * 1fr),
              column-gutter: 14pt,
              align: (top + left, top + left),
              media-el, text-el,
            )
          }
        } else {
          if has-aside {
            grid(
              columns: (text-pct * 1fr, media-pct * 1fr, aside-pct * 1fr),
              column-gutter: 14pt,
              align: (top + left, top + left, top + left),
              text-el, media-el, aside-el,
            )
          } else {
            grid(
              columns: (text-pct * 1fr, media-pct * 1fr),
              column-gutter: 14pt,
              align: (top + left, top + left),
              text-el, media-el,
            )
          }
        }
      } else if eff-pos == "bottom" {
        stack(
          spacing: 8pt,
          text-el,
          media-el,
          ..(if has-aside { (aside-el,) } else { () })
        )
      } else {
        stack(
          spacing: 8pt,
          media-el,
          text-el,
          ..(if has-aside { (aside-el,) } else { () })
        )
      }
    })
  ]

  if is-floating {
    place-full-float(blk, box-el)
  } else {
    box-el
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

#let render-kpi-cards-box(blk, is-margin: false, allow-float: true) = {
  let is-floating = allow-float and (not is-margin) and (blk.at("layout", default: "full") == "full") and (not blk.at("_inline_full", default: false))
  let title-txt = str(blk.at("title", default: "")).trim()
  let sub-txt = str(blk.at("subtitle", default: "")).trim()
  let src-txt = str(blk.at("source", default: "")).trim()
  let cards = blk.at("cards", default: ())
  let style-preset = blk.at("style_preset", default: "tint")
  let req-cols = int(blk.at("columns_count", default: 0))

  let title-sz = if is-margin { 8.8pt } else { 10pt }
  let sub-sz = if is-margin { 7.6pt } else { 8.3pt }

  let render-single-kpi-card(card, card-h: auto) = {
    let accent-col = rgb(card.at("accent_hex", default: "#002855"))
    let tint-col = rgb(card.at("tint_hex", default: "#EEF3F8"))
    let badge-col = rgb(card.at("badge_hex", default: "#DCE6F2"))
    let border-col = rgb(card.at("border_hex", default: "#C2D1E2"))

    let card-fill = if style-preset == "tint" {
      tint-col
    } else if style-preset == "card_accent_left" {
      rgb("#FAFBFD")
    } else {
      white
    }

    let card-stroke = if style-preset == "tint" {
      0.6pt + border-col
    } else if style-preset == "card_accent_top" {
      (top: 2.2pt + accent-col, left: 0.6pt + lukb-border, right: 0.6pt + lukb-border, bottom: 0.6pt + lukb-border)
    } else if style-preset == "card_accent_left" {
      (left: 2.8pt + accent-col, top: 0.6pt + lukb-border, right: 0.6pt + lukb-border, bottom: 0.6pt + lukb-border)
    } else {
      0.6pt + lukb-border
    }

    let icon-path = resolve-asset-path(card.at("resolved_icon", default: ""))
    let lbl-txt = str(card.at("label", default: "")).trim()
    let val-txt = str(card.at("value", default: "")).trim()
    let sub-card-txt = str(card.at("subtext", default: "")).trim()

    let icon-box-sz = if is-margin { 17pt } else { 20pt }
    let icon-img-sz = if is-margin { 10.5pt } else { 12.5pt }
    let pad-x = if is-margin { 7.5pt } else { 9.5pt }
    let pad-y = if is-margin { 6.5pt } else { 8.5pt }

    block(
      width: 100%,
      height: card-h,
      breakable: false,
      fill: card-fill,
      stroke: card-stroke,
      radius: 2.5pt,
      inset: (x: pad-x, y: pad-y),
      above: 0pt,
      below: 0pt,
    )[
      #set par(justify: false, leading: 0.34em, spacing: 0.35em)
      #set text(hyphenate: false)
      #if icon-path != "" or lbl-txt != "" [
        #if icon-path != "" and lbl-txt != "" [
          #grid(
            columns: (auto, 1fr),
            column-gutter: if is-margin { 5.5pt } else { 7pt },
            align: (left + horizon, left + horizon),
            box(
              width: icon-box-sz,
              height: icon-box-sz,
              fill: badge-col,
              radius: 3.5pt,
              align(center + horizon)[#image(icon-path, width: icon-img-sz, height: icon-img-sz)]
            ),
            text(
              font: font-heading,
              weight: "medium",
              size: if is-margin { 7.3pt } else { 7.9pt },
              fill: lukb-muted,
            )[#lbl-txt]
          )
        ] else if icon-path != "" [
          #box(
            width: icon-box-sz,
            height: icon-box-sz,
            fill: badge-col,
            radius: 3.5pt,
            align(center + horizon)[#image(icon-path, width: icon-img-sz, height: icon-img-sz)]
          )
        ] else [
          #text(
            font: font-heading,
            weight: "medium",
            size: if is-margin { 7.3pt } else { 7.9pt },
            fill: lukb-muted,
          )[#lbl-txt]
        ]
      ]
      #if val-txt != "" [
        #block(
          above: if icon-path != "" or lbl-txt != "" { if is-margin { 4pt } else { 5.5pt } } else { 0pt },
          below: 0pt,
        )[
          #set par(leading: 0.28em, justify: false)
          #text(
            font: font-heading,
            weight: "medium",
            size: if is-margin { 11.2pt } else { 13.2pt },
            fill: lukb-navy,
          )[#val-txt]
        ]
      ]
      #if sub-card-txt != "" [
        #block(
          above: if is-margin { 2.5pt } else { 3.5pt },
          below: 0pt,
        )[
          #set par(leading: 0.34em, justify: false)
          #text(
            font: font-body,
            weight: "light",
            size: if is-margin { 7.2pt } else { 7.9pt },
            fill: lukb-muted,
          )[#sub-card-txt]
        ]
      ]
    ]
  }

  let kpi-box = block(
    width: 100%,
    breakable: false,
    above: if is-floating { 0pt } else if is-margin { 0.45em } else { 1.15em },
    below: if is-floating { 0pt } else if is-margin { 0.6em } else { 1.15em },
  )[
    #if title-txt != "" or sub-txt != "" [
      #render-box-title-subtitle(
        title-txt,
        sub-txt,
        title-sz,
        sub-sz,
        is-margin: is-margin,
        title-below-no-sub: if is-margin { 4.5pt } else { 6pt },
        sub-below: if is-margin { 4.5pt } else { 6pt },
        sticky-blocks: true,
      )
    ]
    #if cards.len() > 0 [
      #layout(bounds => {
        let max-by-w = if is-margin or bounds.width < 200pt { 1 } else if bounds.width < 340pt { 2 } else { 4 }
        let wanted = if req-cols > 0 { calc.min(req-cols, cards.len()) } else { calc.min(cards.len(), 4) }
        let eff-cols = calc.max(1, calc.min(wanted, max-by-w))
        let col-gutter = if is-margin { 6pt } else { 9pt }
        let row-gutter = if is-margin { 6pt } else { 9pt }
        let card-w = (bounds.width - (eff-cols - 1) * col-gutter) / eff-cols
        let card-rows = cards.chunks(eff-cols)
        stack(
          spacing: row-gutter,
          ..card-rows.map(row-cards => {
            let max-h = row-cards.map(c => measure(block(width: card-w, render-single-kpi-card(c))).height).fold(0pt, (a, b) => calc.max(a, b))
            grid(
              columns: range(eff-cols).map(_ => 1fr),
              column-gutter: col-gutter,
              align: top + left,
              ..row-cards.map(c => render-single-kpi-card(c, card-h: max-h))
            )
          })
        )
      })
    ]
    #render-box-source(src-txt, is-margin: is-margin)
  ]

  if is-floating {
    place-full-float(blk, kpi-box)
  } else {
    kpi-box
  }
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
    #let render-glossary-entry(item) = {
      let term = item.at("term", default: "")
      let def = item.at("definition", default: "")
      [
        #set par(leading: 0.28em, justify: false)
        #text(font: font-heading, weight: "medium", size: 7.8pt, fill: lukb-navy)[#term]
        #h(3pt)
        #text(font: font-body, weight: "light", size: 7.6pt, fill: lukb-muted)[—]
        #h(3pt)
        #text(font: font-body, weight: "light", size: 7.6pt, fill: lukb-text)[#def]
      ]
    }
    #if two-columns [
      #grid(
        columns: (1fr, 1fr),
        column-gutter: 14pt,
        row-gutter: 4pt,
        ..items.map(item => render-glossary-entry(item))
      )
    ] else [
      #for item in items [
        #block(above: 2.5pt, below: 2.5pt)[#render-glossary-entry(item)]
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

    let linked-content = if purl != "" {
      link(purl)[#line-text]
    } else {
      line-text
    }

    grid(
      columns: (auto, 1fr),
      column-gutter: 6pt,
      text(font: font-body, weight: "medium", size: 8.5pt, fill: lukb-blue)[#sym.dash.en],
      block[
        #set par(justify: false, leading: 0.35em)
        #linked-content
      ]
    )
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

#let get-typst-attr(blk, key, default: "") = blk.at(key + "_typst", default: blk.at(key, default: default))

#let maybe-place-bottom(blk, el, can-float) = {
  if can-float and blk.at("layout", default: "column") == "full" {
    place(bottom, scope: "parent", float: true, el)
  } else {
    el
  }
}

#let render-textbox-container(breakable: true, above: 1.05em, below: 1.05em, body) = block(
  width: 100%,
  breakable: breakable,
  fill: rgb("#EBF3FA"),
  stroke: 0.6pt + lukb-navy,
  inset: (x: 10pt, y: 9pt),
  radius: 2pt,
  above: above,
  below: below,
  body,
)

#let render-single-block(
  blk,
  in-box: false,
  inline-full: false,
  is-margin: false,
  allow-float: true,
  table-style: "navy",
  callout-accent: lukb-cyan,
  quote-accent: lukb-cyan,
  heading-below: 0.68em,
) = {
  let can-float = allow-float and (not in-box) and (not inline-full)
  if blk.type == "colbreak" {
    colbreak()
  } else {
    let rendered = if blk.type == "heading" {
      let out-lvl = blk.at("outline_level", default: none)
      render-heading(blk.level, blk.text, outline-level: out-lvl, below-space: heading-below)
    } else if blk.type == "richtext" {
      if blk.typst_markup != none and blk.typst_markup.trim() != "" {
        eval(blk.typst_markup, mode: "markup")
        parbreak()
      }
    } else if blk.type == "callout" {
      render-callout(blk.title, blk.typst_markup, accent-color: callout-accent)
    } else if blk.type in ("figure", "db_chart", "custom_chart") {
      let bcopy = blk
      if in-box {
        bcopy.insert("layout", "column")
      } else if inline-full {
        bcopy.insert("_inline_full", true)
      }
      render-figure-box(bcopy, is-margin: is-margin, allow-float: allow-float)
    } else if blk.type == "table" {
      let bcopy = blk
      if in-box {
        bcopy.insert("layout", "column")
      } else if inline-full {
        bcopy.insert("_inline_full", true)
      }
      render-table-box(bcopy, is-margin: is-margin, allow-float: allow-float, style-variant: table-style)
    } else if blk.type == "media_text" {
      let bcopy = blk
      if in-box {
        bcopy.insert("layout", "column")
      } else if inline-full {
        bcopy.insert("_inline_full", true)
      }
      render-media-text-box(bcopy, is-margin: is-margin, allow-float: allow-float)
    } else if blk.type == "kpi_cards" {
      let bcopy = blk
      if in-box {
        bcopy.insert("layout", "column")
      } else if inline-full {
        bcopy.insert("_inline_full", true)
      }
      render-kpi-cards-box(bcopy, is-margin: is-margin, allow-float: allow-float)
    } else if blk.type == "textbox_group" {
      let has-colbreak = blk.children.any(c => c.type == "colbreak")
      layout(bounds => {
        let inner-content = [
          #for child in blk.children [
            #render-single-block(
              child,
              in-box: true,
              is-margin: is-margin,
              allow-float: allow-float,
              table-style: table-style,
              callout-accent: callout-accent,
              quote-accent: quote-accent,
              heading-below: heading-below,
            )
          ]
        ]
        let box-breakable = render-textbox-container(breakable: true, inner-content)
        // Typografische Regel:
        // Kurze Boxen (1 Kind-Element und <= 90pt / ca. 3.2cm) ohne manuellen Umbruch werden zusammengehalten.
        let is-short-single-box = if blk.children.len() <= 1 {
          measure(box-breakable, width: bounds.width).height <= 90pt
        } else {
          false
        }
        if (not has-colbreak) and is-short-single-box {
          render-textbox-container(breakable: false, inner-content)
        } else {
          box-breakable
        }
      })
    } else if blk.type == "spacer" {
      let h-mm = blk.at("height_mm", default: 8)
      block(height: h-mm * 1mm, width: 100%)[]
    } else if blk.type == "quote" {
      let q-box = render-quote-box(
        get-typst-attr(blk, "quote"),
        get-typst-attr(blk, "author"),
        get-typst-attr(blk, "source"),
        accent-color: quote-accent,
      )
      maybe-place-bottom(blk, q-box, can-float)
    } else if blk.type == "divider" {
      render-divider(blk.at("style", default: "solid"))
    } else if blk.type == "footnotes" {
      let fn-box = render-footnotes-box(
        get-typst-attr(blk, "title", default: "Anmerkungen & Quellen"),
        get-typst-attr(blk, "items", default: ()),
      )
      maybe-place-bottom(blk, fn-box, can-float)
    } else if blk.type == "glossary" {
      let g-box = render-glossary-box(
        get-typst-attr(blk, "title", default: "Glossar & Begriffserklärungen"),
        get-typst-attr(blk, "items", default: ()),
      )
      maybe-place-bottom(blk, g-box, can-float)
    } else if blk.type == "publications" {
      let pub-box = render-publications-box(
        get-typst-attr(blk, "title", default: "Weitere Publikationen"),
        get-typst-attr(blk, "items", default: ()),
      )
      maybe-place-bottom(blk, pub-box, can-float)
    }
    cms-link-block(blk, rendered)
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

    let has-full-float = items.any(it => (it.type in ("figure", "db_chart", "custom_chart", "table", "media_text", "kpi_cards")) and (it.at("layout", default: "column") == "full"))
    let manual-colbreak-idx = items.position(it => it.type == "colbreak")
    let has-internal-colbreak = items.any(it => it.type == "textbox_group" and it.children.any(c => c.type == "colbreak"))

    if has-full-float or has-internal-colbreak {
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

      if items.len() >= 2 and items.len() <= 24 {
        let item-heights = items.map(it => {
          if it.type == "spacer" {
            (it.at("height_mm", default: 8) * 1mm)
          } else if it.type == "colbreak" {
            0pt
          } else {
            measure(block(width: col-w, render-item(it))).height
          }
        })
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
      let is-full = (it.type in ("figure", "db_chart", "custom_chart", "table", "media_text", "kpi_cards")) and (it.at("layout", default: "column") == "full")
      if not is-full {
        let ih = if it.type == "spacer" {
          (it.at("height_mm", default: 8) * 1mm)
        } else if it.type == "colbreak" {
          0pt
        } else {
          measure(block(
            width: col-w,
            render-single-block(
              it,
              in-box: false,
              callout-accent: callout-accent,
              quote-accent: quote-accent,
              heading-below: heading-below,
            )
          )).height
        }
        pending-sum-h = pending-sum-h + ih + 8pt
        if it.type in ("figure", "db_chart", "custom_chart", "callout", "quote") and ih > pending-max-indiv-h {
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
        } else if it.type == "kpi_cards" {
          measure(block(width: bounds.width, render-kpi-cards-box(b-probe))).height
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
      let is-full-block = (blk.type in ("figure", "db_chart", "custom_chart", "table", "media_text", "kpi_cards")) and (blk.at("layout", default: "column") == "full")
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

#let compute-tufte-row-gutters(rows) = {
  if rows.len() > 1 {
    range(rows.len() - 1).map(idx => {
      let prev-row = rows.at(idx)
      let next-row = rows.at(idx + 1)
      let prev-last = if prev-row.left.len() > 0 { prev-row.left.last() } else { none }

      if prev-last != none and prev-last.type == "heading" {
        // Vorherige Zeile endete mit einer Überschrift:
        // Exakter Unterabstand der Überschrift (6pt bei H1, 0.65em bei H2/H3)
        let lvl = prev-last.at("level", default: 2)
        if lvl == 1 { 6pt } else { 0.65em }
      } else {
        // Standard-Abstand im Tufte-Fliesstext (par spacing bzw. heading above-space):
        // Exakt 1.8em, identisch zum vertikalen Abstand innerhalb derselben Zeile.
        1.8em
      }
    })
  } else {
    1.8em
  }
}

#let render-tufte-single-block(blk, is-margin: false, build-rows-fn: none) = {
  if blk.type == "colbreak" {
    // Wird auf Run-Ebene als Seitenumbruch behandelt
  } else {
    let rendered = if blk.type == "heading" {
      let out-lvl = blk.at("outline_level", default: none)
      render-heading(
        blk.level,
        blk.text,
        outline-level: out-lvl,
        h1-size: 13.5pt,
        h2-size: 10.5pt,
        h3-size: 9.6pt,
        above-space: 1.8em,
        h1-below: 6pt,
        below-space: 0.65em,
      )
    } else if blk.type == "richtext" {
      if blk.typst_markup != none and blk.typst_markup.trim() != "" {
        eval(blk.typst_markup, mode: "markup")
        parbreak()
      }
    } else if blk.type == "callout" {
      render-callout(blk.title, blk.typst_markup, accent-color: lukb-cyan, title-size: 9.5pt, body-size: 8.8pt)
    } else if blk.type in ("figure", "db_chart", "custom_chart") {
      render-figure-box(blk, is-margin: is-margin, allow-float: false)
    } else if blk.type == "table" {
      render-table-box(blk, is-margin: is-margin, allow-float: false, style-variant: "tufte")
    } else if blk.type == "media_text" {
      render-media-text-box(blk, is-margin: is-margin, allow-float: false)
    } else if blk.type == "kpi_cards" {
      render-kpi-cards-box(blk, is-margin: is-margin, allow-float: false)
    } else if blk.type == "textbox_group" {
      let visual-children = blk.children.filter(c => c.type in ("figure", "db_chart", "custom_chart", "table"))
      let text-children = blk.children.filter(c => not (c.type in ("figure", "db_chart", "custom_chart", "table")))
      let has-visuals = visual-children.len() > 0
      let has-text = text-children.len() > 0
      let is-split = has-visuals and has-text and (not is-margin)

      render-textbox-container(above: 1.25em, below: 1.25em)[
        #if is-split and build-rows-fn != none [
          #let box-rows = build-rows-fn(blk.children, main-w: tufte-main-w - 10pt, margin-w: tufte-margin-w - 10pt)
          #let box-gutters = compute-tufte-row-gutters(box-rows)
          #grid(
            columns: (1fr, tufte-margin-w),
            column-gutter: tufte-gutter,
            row-gutter: box-gutters,
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
      block(height: h-mm * 1mm, width: 100%)[]
    } else if blk.type == "quote" {
      render-quote-box(
        get-typst-attr(blk, "quote"),
        get-typst-attr(blk, "author"),
        get-typst-attr(blk, "source"),
        accent-color: lukb-gold,
        is-margin: is-margin,
        tufte-style: true,
      )
    } else if blk.type == "divider" {
      render-divider(blk.at("style", default: "solid"))
    } else if blk.type == "footnotes" {
      render-footnotes-box(
        get-typst-attr(blk, "title", default: "Anmerkungen & Quellen"),
        get-typst-attr(blk, "items", default: ()),
      )
    } else if blk.type == "glossary" {
      render-glossary-box(
        get-typst-attr(blk, "title", default: "Glossar & Begriffserklärungen"),
        get-typst-attr(blk, "items", default: ()),
        two-columns: true,
      )
    } else if blk.type == "publications" {
      render-publications-box(
        get-typst-attr(blk, "title", default: "Weitere Publikationen"),
        get-typst-attr(blk, "items", default: ()),
        two-columns: false,
      )
    }
    cms-link-block(blk, rendered)
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
    let is-margin = (it.type in ("figure", "db_chart", "custom_chart", "table", "kpi_cards")) and (it.at("layout", default: "column") == "column")
    if is-margin {
      let mh = measure-margin(it)
      let anchor-id = it.at("anchor_to", default: none)
      let explicit-anchor-pos = if anchor-id != none and anchor-id != "" and anchor-id != "auto" {
        curr-left.position(x => x.at("id", default: "") == anchor-id)
      } else {
        none
      }

      if explicit-anchor-pos != none {
        // Explizite Anker-Verknüpfung:
        // Zielblock in curr-left gefunden! Trennt exakt vor dem gewählten Anker-Block.
        // User kann so bewusst wählen, ob das Randelement an der Überschrift oder am Absatz ausgerichtet wird.
        let split-at = explicit-anchor-pos
        if split-at > 0 {
          let flushed-left = curr-left.slice(0, split-at)
          let anchor-left = curr-left.slice(split-at)
          rows.push((left: flushed-left, right: curr-right))
          curr-left = anchor-left
          left-h = anchor-left.map(measure-main).fold(0pt, (a, b) => a + b)
          curr-right = (it,)
          right-h = mh
        } else {
          // Der Anker steht bereits an erster Position in dieser Zeile
          curr-right.push(it)
          right-h = right-h + mh
        }
      } else if curr-right.len() == 0 {
        // Erstes Rand-Element in dieser Zeile (Heuristik ohne expliziten Anker):
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
      let has-box-visuals = (blk.type == "textbox_group") and blk.children.any(c => c.type in ("figure", "db_chart", "custom_chart", "table", "media_text", "kpi_cards"))
      let is-full = ((blk.type in ("figure", "db_chart", "custom_chart", "table", "media_text", "kpi_cards", "quote", "footnotes", "glossary", "publications")) and (blk.at("layout", default: "column") == "full")) or ((blk.type == "textbox_group") and (has-box-visuals or blk.at("layout", default: "column") == "full"))
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
        let gutters = compute-tufte-row-gutters(rows)

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

// ============================================================================
// Einspaltiger Hauptteil (für advisory_onecol)
// ============================================================================

#let render-one-column-body(
  blocks,
  callout-accent: lukb-cyan,
  quote-accent: lukb-cyan,
  heading-below: 0.65em,
) = {
  for blk in blocks {
    if blk.type == "colbreak" {
      pagebreak(weak: true)
    } else {
      render-single-block(
        blk,
        in-box: false,
        inline-full: true,
        allow-float: false,
        callout-accent: callout-accent,
        quote-accent: quote-accent,
        heading-below: heading-below,
      )
    }
  }
}
