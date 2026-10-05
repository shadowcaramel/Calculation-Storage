---
name: parse-paper-table
description: >-
  Read an irregular LaTeX table from paper source and write a parsed number
  grid (parsed JSON) for Calculation Storage paper pages. Use when attaching a
  table from a .tex paper, filling table1.parsed.json, or deciding whether a
  printed number matches a stored calculation directly or was derived (for
  example an extrapolated energy minus a threshold).
---

# Parse a paper table

Paper tables have no shared template. Do not add a `tabular` parser to
`paper_storage`. Read the source, write JSON, and leave the build to display it.

The screenshot stays the picture of the published table. The `.tex` fragment
stays the source. The parsed file is only the numbers.

## When this applies

Use this skill when the user attaches a table from paper source, asks for a
parsed grid, or asks whether a printed value matches a stored bundle.

Do not run it from `python -m paper_storage build`. That command only reads
JSON that is already on disk.

## Read

1. Open the `.tex` fragment named in `papers.json` (`materials[].latex`), or the
   larger source file the user points at.
2. Find the table they mean. Markup such as `\begin{table}`, `\caption`,
   `\cite`, `\raisebox`, `\hline`, and `\multicolumn` is not a cell.
3. Keep a rectangular grid. Header text is the source text after that markup is
   removed, not a translation. A math header also gets a short `latex` string
   with the dollars removed, for example `N_{\max}^{u}`.
4. Every numeric cell keeps the printed `text`, including uncertainty in
   parentheses (`-32.034(4)`), and a `value` that is the central number. Do not
   invent a cell that is not in the source. Leave a non-numeric cell with
   `text` only.

## Write

Write `papers/<paper-id>/<material-id>.parsed.json` next to the `.tex` file
(the same stem: `table1.tex` → `table1.parsed.json`). UTF-8. Do not overwrite
`papers.json` links unless the user asks.

```json
{
  "caption": "Caption text from the source, with \\cite{key} kept as [key].",
  "columns": [
    {"id": "nmax", "text": "Nmax^u", "latex": "N_{\\max}^{u}"},
    {"id": "Our calculations", "text": "наши расчеты"}
  ],
  "rows": [
    {
      "cells": [
        {"text": "18", "value": 18},
        {"text": "-32.034(4)", "value": -32.034}
      ]
    }
  ]
}
```

`columns[].id` is the stable name a link uses. `text` is what the page shows.
Match an existing link's `column` to either field.

## Link a cell to a calculation

Only when the user wants the connection. One link in `papers.json`:

```json
{
  "label": "6Li, our calculation, Nmax = 18",
  "result": "<bundle id>",
  "material": "table1",
  "row": 4,
  "column": "Our calculations",
  "compare": "direct"
}
```

`row` is the 0-based index into `rows` (header rows are columns, not data).

- `direct` — the printed central value is the same quantity as the stored
  median. A later lint warns if they disagree past the last printed digit.
  The 2024 Moscow University Physics Bulletin / Vestnik Table 1 is this case.
- `derived` — the printed value was adjusted before comparison, for example an
  extrapolated energy minus a threshold energy. Set `note` to that adjustment.
  The numbers are shown side by side and are not required to agree. A missing
  note is a warning. A numeric difference is not.

Do not mark `direct` when the paper subtracted a threshold or otherwise changed
the quantity. Other columns (variational minima, another group's results) stay
in the grid with no link unless the user asks.
