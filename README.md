# EO-FM Living Atlas Auto

Automation-first version of the EO-FM Living Atlas.

The website frontend is the same as the polished atlas: catalogue table, filters, access labels, model details, interactive landscape, method page, add-entry page, and a benchmark/dataset tab. The difference is the backend: the live data is generated from upstream RSFM lists and enriched with an LLM.

## What this repo does

```text
Upstream awesome lists
  ↓
Parse model / benchmark / dataset rows
  ↓
Deduplicate by paper, DOI, arXiv, GitHub, Hugging Face
  ↓
Fetch paper metadata, arXiv abstracts/PDF excerpts, Crossref metadata, GitHub README excerpts
  ↓
Use an LLM to extract structured fields
  ↓
Generate data/catalogue.json and data/benchmarks.json
  ↓
Website + landscape update automatically
```

## Required secret

This final version requires an OpenAI API key because the atlas needs paper-reading enrichment for modalities, architecture, tasks, access, modelling paradigm, and landscape fields.

Add it here:

```text
Settings → Secrets and variables → Actions → Secrets → New repository secret

Name: OPENAI_API_KEY
Value: your key
```

Optional repository variable:

```text
Settings → Secrets and variables → Actions → Variables → New repository variable

Name: OPENAI_MODEL
Value: gpt-4o-mini
```

Do not commit API keys to this repo.

## Automation schedule

The workflow runs automatically:

```text
On push to main
1st and 15th of every month at 04:17 UTC
```

So the first upload/push to `main` bootstraps the catalogue immediately.

## Public data files

```text
data/catalogue.json      # model catalogue used by Catalogue and Landscape
data/benchmarks.json     # benchmark/dataset catalogue used by Benchmarks tab
data/metadata.json       # generation metadata
data/candidates/         # raw/enriched candidate records and duplicate reports
```

The previous manually curated 74-entry catalogue is preserved only as backup:

```text
data/manual_seed_catalogue.json
```

It is not used as the live catalogue in this upstream-first version.

## Duplicate handling

The sync merges records when they share strong evidence:

```text
same arXiv ID
same DOI
same normalized paper URL
same GitHub repository
same Hugging Face repository
```

Weak name-only matches are not merged automatically. They are written to possible-duplicate reports for review, so different releases such as `Prithvi-EO-1.0` and `Prithvi-EO-2.0` are not accidentally collapsed.

## Scientific status

Generated entries are marked as auto-derived/candidate-style records. They are useful for discovery and landscape generation, but should still be reviewed before being cited as verified curated data.
