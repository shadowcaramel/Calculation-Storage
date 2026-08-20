# `result.json` field registry

Every field ever stored in a result bundle, with the schema version it appeared
in and the version it was retired in (if any). This file is the reason an old
record stays interpretable: when a field's meaning is unclear a year from now,
look it up here.

**Rules for changing the schema**

1. **Additive only.** New fields are optional. Old records simply lack them and
   views render the union of all fields, showing a blank where a record has none.
   No existing record may become invalid because the schema grew.
2. **Deprecate, never delete.** When a feature is retired, stop *writing* the
   field but keep reading it, and record the retirement version here.
3. **Bump `schema_version` only when meaning changes**, not when a field is
   added. A meaning change also needs a migration in the reader repo
   (`Calculation-Storage`, `results_library/migrations/`).
4. **Store the method next to the value.** Anything that changes how a number
   was computed (uncertainty definition, aggregation, transition direction) is
   itself a field, so values from different months are never silently compared.

Current version: **1**

---

## Top level

| Field | Since | Retired | Type | Meaning |
| --- | --- | --- | --- | --- |
| `schema_version` | 1 | | int | Version of this record's layout. |
| `id` | 1 | | str | `{nucleus}/{state}/{observable}/{run_stamp}`. Stable forever; notes and links hang off it. |
| `family` | 1 | | str | First three id segments. Groups all variants of one physics question. |
| `subject` | 1 | | table | What the result is about. See below. |
| `reference` | 1 | | table | What a relative quantity is measured against. Absent for absolute quantities. |
| `observable` | 1 | | table | The measured quantity and its display forms. |
| `computed` | 1 | | table | The number and its uncertainty. |
| `variant` | 1 | | table | The setup that produced the number. |
| `provenance` | 1 | | table | Where the number came from. |
| `status` | 1 | | str | `probing` \| `working` \| `published` \| `superseded`. Written as `probing`; promotion happens in `annotations.toml`, which wins on conflict. |
| `available` | 1 | | list[str] | Which artifact kinds actually exist, so views only offer real downloads. |
| `artifacts` | 1 | | table | Artifact key to filename, relative to the bundle directory. |
| `column_labels` | 1 | | table | Display forms for input columns and observables, copied from `[postprocessing.prediction_plots.labels]` at capture. Each entry has `display`, `unicode`, optional `latex` and `unit`. Views use these so HTML shows `ħΩ` rather than `hOmega`. Older records lack this table; the catalog then applies the schema defaults. |

## `subject`

| Field | Since | Retired | Type | Meaning |
| --- | --- | --- | --- | --- |
| `kind` | 1 | | str | `state` or `transition`. |
| `nucleus` | 1 | | str | `{A}{Element}`, e.g. `16C`. Present when `kind = "state"`. |
| `state` | 1 | | table | State record. Present when `kind = "state"`. |
| `initial` | 1 | | table | `{nucleus, state}`. Present when `kind = "transition"`. |
| `final` | 1 | | table | `{nucleus, state}`. Present when `kind = "transition"`. |

Cross-nucleus quantities are **not** transitions. A relative energy is
asymmetric (one primary subject, one reference), so both transition endpoints
must share a nucleus and cross-nucleus cases use `reference` instead.

## State record (`subject.state`, `subject.initial.state`, `reference.state`)

| Field | Since | Retired | Type | Meaning |
| --- | --- | --- | --- | --- |
| `J2` | 1 | | int | **Twice** the total angular momentum. `J2 = 5` means J = 5/2. |
| `parity` | 1 | | str | `+` or `-`. |
| `T2` | 1 | | int | **Twice** the isospin. Always declared explicitly, never derived from the nucleus. |
| `index` | 1 | | int | `n`, ordinal among states of the same `J^pi`, counted by increasing energy from 1. |

Spin and isospin are stored doubled so they remain integers and no float
rounding can enter an identity.

`index` is always stored and always appears in the slug, even at `n = 1`.
Whether a second state with the same quantum numbers exists is a property of the
dataset, not of the state, so omitting the index would let a later calculation
retroactively change an existing id and break every note hanging off it. Display
labels omit it at `n = 1`, which is a dataset-independent rule.

## `reference`

| Field | Since | Retired | Type | Meaning |
| --- | --- | --- | --- | --- |
| `nucleus` | 1 | | str | Reference nucleus. Omitted from slugs and labels when equal to the subject's. |
| `state` | 1 | | table | Reference state record. |
| `alias` | 1 | | str | Short name used in the slug instead of a full state slug, e.g. `gs`. |
| `convention` | 1 | | table | Anything that changes the reference value, e.g. `evaluated_at_hOmega = 16`. |

`convention` exists because the same state referenced to the ground state
evaluated at one hOmega or another yields different numbers. Those must not
collide, so the reference feeds both the observable slug and `variant_hash`.

## `observable`

| Field | Since | Retired | Type | Meaning |
| --- | --- | --- | --- | --- |
| `slug` | 1 | | str | Path-safe name. `B(E2)` becomes `BE2`, `Mn/Mp` becomes `Mn_over_Mp`. |
| `name` | 1 | | str | Name as used in the data, e.g. `Erel`. |
| `latex` | 1 | | str | Math-mode label for tables and figures. |
| `unicode` | 1 | | str | Plain-text display form for HTML and Excel, e.g. `Eᵣₑₗ`. Derived from `mathtext` / `latex` at capture. An explicit value is an optional override. |
| `units` | 1 | | str | Physical units, empty string for dimensionless. |
| `direction` | 1 | | str | `up` or `down` for transition strengths. B(E2) up and down differ by `(2J_f+1)/(2J_i+1)`, so an unlabelled value is ambiguous. |

## `computed`

| Field | Since | Retired | Type | Meaning |
| --- | --- | --- | --- | --- |
| `median` | 1 | | float | Central value: ensemble median at `Nmax_final`. |
| `Q1`, `Q3` | 1 | | float | First and third quartiles across models. |
| `err_low`, `err_high` | 1 | | float | Asymmetric uncertainty, `median - Q1` and `Q3 - median`. |
| `IQR` | 1 | | float | `Q3 - Q1`. |
| `N_models` | 1 | | int | Models surviving filtering and contributing to the statistics. |
| `Nmax_final` | 1 | | float | Nmax at which the extrapolated value is read off. |
| `uncertainty_method` | 1 | | str | How the uncertainty was defined, e.g. `IQR`. |
| `homega_aggregation` | 1 | | str | How each model's ħΩ dependence was collapsed, e.g. `min`, `median`. |
| `KDE_mode` | 1 | | float | Mode of the kernel density estimate, when KDE is enabled. |
| `HDR_low`, `HDR_high` | 1 | | float | Highest-density region bounds, when enabled. |

## `variant`

| Field | Since | Retired | Type | Meaning |
| --- | --- | --- | --- | --- |
| `bounds` | 1 | | table | Data-selection bounds per input column, e.g. `Nmax = [4, 18]`. |
| `selection_set` | 1 | | str | Which filtered model subset the statistics used, e.g. `final`. |
| `filter_criteria` | 1 | | list[str] | Filtering criteria applied. |
| `reference_convention` | 1 | | table | Echo of `reference.convention`, so the hash covers it. |
| `config_name` | 1 | | str | Pipeline configuration name, e.g. `0p2/Nmax=[4,18]_hOmega=[8,50]`. |
| `variant_hash` | 1 | | str | First 8 hex chars of a SHA-256 over the rest of this block. Identical setups across runs share a hash. |

## `provenance`

| Field | Since | Retired | Type | Meaning |
| --- | --- | --- | --- | --- |
| `code_version` | 1 | | str | Git commit or tag of the pipeline that produced the result. |
| `created_at` | 1 | | str | ISO-8601 UTC timestamp. |
| `run_dir` | 1 | | str | Name of the Tier 1 run directory, which may later be pruned. |
| `config_snapshot` | 1 | | str | Filename of the frozen config inside the run directory. |
| `source_workbook` | 1 | | str | Prepared workbook the data came from, taken from config paths. |
| `source_sheet` | 1 | | str | Sheet within that workbook. |

Nothing in `provenance` is scraped from inside a workbook; these come from the
config the pipeline already reads.

## `annotations.toml` (human layer, not part of `result.json`)

| Field | Since | Type | Meaning |
| --- | --- | --- | --- |
| `status` | 1 | str | Overrides the record's `status`. |
| `title` | 1 | str | Human title for views. |
| `tags` | 1 | list[str] | Free tags, e.g. `hOmega-scan`. |
| `note` | 1 | str | Free-form note about the calculation. |
| `outcome` | 1 | str | Why the result was or was not interesting. Deliberately separate from `note`: this is the first thing forgotten and the main reason to keep exploratory runs. |

This file is hand-edited and **never** auto-overwritten. The catalog build only
merges it in, keyed by result id.
