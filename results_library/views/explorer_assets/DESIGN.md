# Explorer design: modern Bauhaus

The explorer is a working instrument for reading calculation results, so the
style follows the Bauhaus rule that form follows function: every colour, shape
and line has one job, and nothing is decoration. The tokens live at the top of
`app/explorer.css`; this file is the reasoning behind them.

## Principles

1. **Colour means something.** The three primaries are signals, never
   ornament. Everything else is ink on paper.
2. **Shape doubles colour.** Status and series are told apart by a geometric
   mark (circle, square, triangle, diamond) as well as by colour, so the page
   still reads in greyscale, on a projector, or with colour blindness.
3. **Visible structure.** Panels are drawn with a 2 px ink rule and square
   corners. There are no soft shadows, gradients, or rounded blobs. Hairlines
   (1 px, 14 % ink) separate rows inside a panel.
4. **Strong scale contrast.** Few sizes, far apart: a heavy geometric
   headline, small tracked capitals for labels, a neutral text face for
   reading. Numbers are set in the geometric display face with tabular
   lining figures, so they belong to the same system as the headings.
5. **Asymmetric grid.** An 8 px base unit. The main view leads with the one
   thing that matters (the value, the chart); bookkeeping such as library
   statistics goes to the foot of the page.

## Colour

| Token | Light | Dark | Job |
|---|---|---|---|
| `--paper` | `#F3EFE6` | `#121212` | page ground |
| `--surface` | `#FBF9F4` | `#1B1B1A` | panels |
| `--sunk` | `#E9E4D8` | `#262624` | wells, empty cells |
| `--ink` | `#141414` | `#EFEBE2` | text and structural rules |
| `--blue` | `#1F4FA0` | `#6F9BFF` | Modern library |
| `--red` | `#D52B1E` | `#FF6A5C` | Legacy library, superseded |
| `--yellow` | `#F2B807` | `#FFCB3D` | Papers, the headline value, focus |

The active section sets `--acc` (fill) and `--on-acc` (text on that fill):
blue and red carry paper-coloured text, yellow carries ink.

## Status marks

| Status | Mark |
|---|---|
| published | solid ink circle |
| working | yellow triangle |
| probing | hollow square |
| superseded | red square |

## Series (selection sets in the Scan plot)

Series *i* uses colour `--s{i}` and shape `i mod 4`: circle, square,
triangle, diamond. The family headline sits on a yellow disc; the selected
result gets an ink ring.

## Type

| Role | Face | Setting |
|---|---|---|
| Display (h1, wordmark) | Montserrat 800 | uppercase, tight |
| Section titles, labels | Montserrat 700 | uppercase, 0.08 to 0.12 em tracking |
| Reading text | Inter | 14 px / 1.45 |
| Numbers and values | Montserrat 600 (700 for the headline value) | tabular lining figures; values typeset by KaTeX in this face |
| Ids, tags, code | IBM Plex Mono | |

All faces are vendored under `app/fonts/` (SIL Open Font License), because
the page opens over `file://` with no network. Montserrat comes from TeX Live;
it covers Cyrillic, so the Russian captions in papers render in the same face.

## Logo

A staircase of square cells, the shape of the light-nuclei corner of the Z–N
chart. Seven cells are ink; three carry the primaries: blue (Modern) at the
bottom, red (Legacy) in the middle, yellow (Papers) at the top. Ink cells are
solid, never outlined, so the mark still reads at 16 px; they turn paper
coloured on the ink top bar and in a dark browser tab. The top bar draws it
inline with `currentColor`; `app/logo.svg` is the tab icon and switches by
`prefers-color-scheme`. Chosen from six concepts on 2026-10-17; the CS
monogram is the runner-up.

## Components

* **Top bar**: ink band. The brand block starts with the logo (below) at 26 px.
  The tabs (Modern, Legacy, Papers) are flat blocks; the active one fills with
  its colour. The brand block is as wide as the rail (`--rail`), so
  the line after it continues the rail's border.
* **Panel**: 2 px ink border, square corners. The header carries a small
  square in the accent colour and an uppercase title.
* **Button**: 2 px ink border. On hover it inverts to ink with paper text.
* **Chip**: 1.5 px border, square. When pressed it fills with ink.
* **Z–N chart**: square cells. A nucleus with results is outlined in ink;
  the current one fills with the accent colour.
* **Overview**: the title, then the results matrix, then the most recent
  runs, one line per day and nucleus. The Z–N chart stays in the rail. No
  hover preview (it flickered).
* **Results matrix**: nuclei down, observable groups across (energies, radii,
  then everything else folded into one column; the build sets them). Group
  rules are ink, because blue and red name the libraries. A cell shows the
  headline value with its status mark; several states show as a small level
  scheme (excitation energies), two values, or a count and range. A potential
  filter sits in the panel header when the library has more than one.
* **Nucleus page**: a nucleus with excitation energies for two or more
  states opens on its level scheme (one column per J^π, the ground state as
  the baseline, a band for the uncertainty) beside a states table, lowest
  excitation energy first. A switch goes back to the family list. The
  baseline is labelled g.s. only: the catalog does not say which state it is.
* **Search**: its own page per library, opened from the box in the top bar
  or with `/`. Facets replace the family tree in the rail (the Z–N chart
  toggles nuclei, observables sit under their matrix group, last-run years
  are bars); words match names, states as typed (5/2+), potentials,
  selection sets, tags and notes. Each count is what that value would leave.
  The view lives in the hash, so "Copy link to this view" reopens it.
* **Nuclide names**: the mass number is a `<sup>` in the same face as the
  symbol, never a Unicode superscript (the display face lacks ⁴–⁹).
* **Sortable headings**: an arrow after the label; the active one is
  underlined in the accent colour.
* **Footer statistics**: one quiet line of counts and a thin status bar at
  the foot of the overview, below everything you read first.
