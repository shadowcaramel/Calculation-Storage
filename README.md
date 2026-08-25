# Calculation Storage

Reader-side tooling for a library of nuclear-calculation results. It turns a
folder of result bundles into a catalog and three views (static site, Excel
workbook, Datasette).

This repository does **not** hold the calculation data. Bundles live in a
Drive-synced folder (`G:\Shared drives\Calculation results\Calculation storage`). The ensemble
pipeline that *writes* those bundles lives in a separate repository. The two
share an on-disk schema (`schema_version` + `FIELDS.md`), not a Python import.

## The three layers

```
LOCAL DISK (heavy, prunable, not synced)
  ML output/<run>/            models, scalers, raw predictions

SHARED LIBRARY (light, synced, not git)
  bundles/<id>/               result.json + plot + plot data + config snapshot
  sources/<sha256[:16]>/      shared copies of original calculation file(s) and the prepared workbook
  annotations.toml            notes, status, tags (hand-edited) <- SOURCE OF TRUTH
  comparisons.toml            multi-result figures (hand-edited, never overwritten)
  comparisons/                figure files named by comparisons.toml
  catalog.parquet             GENERATED
  catalog.db                  GENERATED
  site/index.html             GENERATED
  calculation_results.xlsx    GENERATED
```

Bundles, `sources/`, `annotations.toml`, `comparisons.toml`, and the comparison
files are inputs. Everything else is regenerated from them, so the generated
files can be deleted at any time without losing anything.

`annotations.toml` is **never written** by any tool here. `comparisons.toml` is
the same: the pipeline never overwrites it. That is what makes the machine
layer safely disposable.

**Do not put the library data in git.** It is mostly binary plots that would
bloat history irreversibly, and a `.git` directory inside a synced folder risks
corruption because sync clients copy object files without understanding git's
consistency requirements. Bundles are immutable by construction, so versioning
them buys little.

## Installing

From this repository:

```bash
pip install -r requirements.txt
```

or, editable, with the optional Datasette extra:

```bash
pip install -e ".[serve,dev]"
```

Set the shared folder to mirrored / available-offline rather than streaming: the
catalog build reads thousands of small JSON files.

## Everyday use

```bash
python -m results_library.cli build --library "G:/Shared drives/Calculation results/Calculation storage"
```

That rebuilds the catalog, the site, and the workbook **from scratch**. There is
no incremental state, so a rebuild is always safe and takes seconds for a few
thousand results. Open `site/index.html` afterwards.

To avoid retyping the path, set it once:

```bash
set RESULTS_LIBRARY=G:/Shared drives/Calculation results/Calculation storage     # Windows
export RESULTS_LIBRARY="G:/Shared drives/Calculation results/Calculation storage"  # POSIX
```

or point at the pipeline config, which already stores the same path:

```bash
python -m results_library.cli build --config "G:/My Drive/!ML/2026 rework/config/config.toml"
```

### Other commands

| Command | Does |
| --- | --- |
| `build` | catalog + site + workbook (use this) |
| `catalog` | just `catalog.parquet` and `catalog.db` |
| `site` | just the static HTML site |
| `excel` | just the workbook |
| `lint` | check the library for inconsistencies |
| `serve` | live filterable UI via Datasette (`pip install datasette`) |

`--library` / `--config` work before or after the subcommand.

## Curating results

Every captured result starts as `probing`. Promote the ones that matter by adding
a table to `annotations.toml` in the shared library, keyed by result id, then
rebuild:

```toml
["16C/2p-T2-n2--to--2p-T2-n1/BE2/2026-08-18_15-02-11_a1b2c3d4"]
status  = "working"          # probing | working | published | superseded
title   = "16C B(E2) (2+,T=2)(2) -> (2+,T=2)"
tags    = ["hOmega-scan", "own-weights"]
note    = "Own sample weights; hOmega 13-40 MeV."
outcome = "Promising; filter kept 261 of 500 models."
```

`outcome` is separate from `note` on purpose: it records *why* an exploratory
result was or was not interesting, which is the first thing forgotten and the
main reason keeping probing runs is worth anything.

The site hides `probing` results by default, and the workbook omits them unless
you pass `--include-probing`.

When more than one selection set was captured for the same trained ensemble
(same run, family, potential, and training bounds), the index and nucleus pages
show a tab bar. The default tab is `final`. Comparing filters means capturing
them on purpose, for example `selection_sets = ["all_models", "final", "conv_Ethr"]`
in `[results_library]` / `[postprocessing.summary]`; extra sets are not captured
automatically.

The main table's Date column is the calculation day (`25 Aug 2026`), taken from
the run stamp. Rows sort newest-first, using the hidden time of day as a
tie-breaker. Nmax is the **training window** `[min, max]`. `Nmax_final` (the
readout) stays on the detail page.

Selection sets of one trained ensemble share a parent folder:

```text
bundles/{nucleus}/{state}/{observable}/{YYYY-MM-DD_HH-MM-SS}_{cohort_hash}/{selection_set}_{variant_hash}/
```

The site still shows a tab bar when more than one set was captured. Older
four-segment bundles (`.../{stamp}_{variant_hash}/` with no selection subfolder)
need a one-shot rewrite:

```bash
python -m results_library.cli migrate-selection-folders --library "G:/Shared drives/Calculation results/Calculation storage"
```

That command also rewrites matching keys in `annotations.toml` and
`comparisons.toml`. Catalog/site builds never move files.

The nucleon-nucleon potential (`identity.potential`, stored on `variant`) appears
after Observable. Older bundles that lack it show as unspecified.

The detail page Files list links every original calculation file copied into
`sources/` (one or many collaborator dumps). If the extracted pivot is a
different file, it is listed separately from those dumps, ahead of the prepared
long workbook.

## Comparison figures

Figures that span several results live next to the annotations, not inside a
bundle. Create `comparisons.toml` in the library root and drop files under
`comparisons/`:

```toml
[[figure]]
title = "Isospin triplet"
file = "comparisons/isospin_triplet.png"
caption = "Daejeon16, same Nmax window."
results = [
  "6He/0p-T1-n2/Erel/2026-08-18_15-02-11_a1b2c3d4",
  "6Li/1p-T0-n1/Erel/2026-08-18_15-02-11_b2c3d4e5",
]
```

Rebuild the site. A Comparisons page is linked from the index; nucleus and
result pages list the figures that mention them. The pipeline never writes this
file.

## Typeset formulas

States, observables, values, and the axis names are typeset in the browser by
KaTeX, which is shipped inside the site under `assets/katex/`. Formulas use the
same Inter face as the surrounding page (Computer Modern is not loaded for
letters and digits). A collaborator opens `site/index.html` from the synced
folder and gets real math: nothing to install, no network. Where the script
does not run, each formula falls back to its Unicode form (`Eᵣₑₗ`, `ħΩ`,
`Nₘₐₓ`), which is also what Excel, CSV, and TSV show.

## Copying tables into LaTeX

Every table on the site has **Copy LaTeX** and **Copy TSV** buttons plus CSV and
`.tex` downloads. These strings are generated from the catalog values, not
scraped from the rendered HTML, which is why pasting them is reliable. Typesetting
never touches them.

The asymmetric-uncertainty form is assembled for you:

```latex
\begin{tabular}{lllccc}
\toprule
State & Observable & Potential & Value & $N_{\mathrm{models}}$ & $N_{\max}$ \\
\midrule
$(5/2^{+},\ T{=}5/2)$ & Erel & Daejeon16 & $2.639^{+0.002}_{-0.002}$ & 744 & [2, 6] \\
\bottomrule
\end{tabular}
```

## Analysis

The catalog is one row per result:

```python
import pandas as pd
catalog = pd.read_parquet(r"G:/Shared drives/Calculation results/Calculation storage/catalog.parquet")

catalog[catalog.nucleus == "6He"].sort_values("run_stamp", ascending=False)

catalog.groupby("family")["median"].agg(["count", "min", "max"])
```

Or with SQL over `catalog.db`:

```sql
SELECT nucleus, state_label, observable, median, err_low, err_high, status
FROM results WHERE status = 'published' ORDER BY nucleus;
```

## Schema and compatibility

Records carry `schema_version`. Field meanings are documented in
`results_library/vendor/results_schema/FIELDS.md`.

Old records are upgraded **on read** by `results_library/migrations/`, never
rewritten on disk. Bundles stay immutable, so a failed build cannot corrupt the
library.

A byte-identical copy of the pipeline's `results_schema` package lives under
`vendor/`. Do not edit those files here. After changing the originals in the
pipeline repository, refresh the copy:

```bash
python -m results_library.sync_schema --source "G:/My Drive/!ML/2026 rework/results_schema"
python -m results_library.sync_schema --check --source "G:/My Drive/!ML/2026 rework/results_schema"
```

`RESULTS_SCHEMA_SOURCE` in the environment is accepted instead of `--source`.

## Tests

```bash
pytest tests/test_results_library.py
```

## License

GNU GPL v3. See [LICENSE](LICENSE).
