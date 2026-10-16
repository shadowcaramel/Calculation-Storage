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
   reading, and a monospaced face for every number.
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
| Numbers, ids, code | IBM Plex Mono | tabular figures |

All faces are vendored under `app/fonts/` (SIL Open Font License), because
the page opens over `file://` with no network. Montserrat comes from TeX Live;
it covers Cyrillic, so the Russian captions in papers render in the same face.

## Components

* **Top bar**: ink band. The wordmark has a circle, a square and a triangle.
  The tabs (Modern, Legacy, Papers) are flat blocks; the active one fills with
  its colour.
* **Panel**: 2 px ink border, square corners. The header carries a small
  square in the accent colour and an uppercase title.
* **Button**: 2 px ink border. On hover it inverts to ink with paper text.
* **Chip**: 1.5 px border, square. When pressed it fills with ink.
* **Z–N chart**: square cells. A nucleus with results is outlined in ink;
  the current one fills with the accent colour.
* **Footer statistics**: one quiet line of counts and a thin status bar at
  the foot of the overview, below everything you read first.
