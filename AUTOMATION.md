# Automation design

This repo turns the EO-FM Living Atlas from a manually seeded website into an upstream-derived, LLM-enriched atlas.

The website frontend stays the same. Only the data generation pipeline changes.

## Trigger

The workflow runs automatically:

- on push to `main`, so the first repo upload runs today;
- on the 1st and 15th of every month at 04:17 UTC.

There is no manual trigger in the final workflow.

## Sources

Configured upstream sources are listed in:

```text
data/upstream_sources.json
```

These point to public markdown/README files such as remote-sensing foundation-model awesome lists.

## Pipeline

```text
Fetch upstream README files
  ↓
Parse markdown tables and linked bullets
  ↓
Normalize paper/code/weights/project URLs
  ↓
Deduplicate by arXiv, DOI, paper URL, GitHub repo, and Hugging Face repo
  ↓
Fetch metadata:
    - arXiv title/abstract/authors
    - bounded arXiv PDF text excerpt
    - Crossref metadata for DOI records
    - GitHub README excerpt for code repos
  ↓
LLM extracts structured fields with a fixed JSON schema:
    - modality tags
    - architecture
    - modelling paradigm
    - downstream tasks
    - access status
    - landscape tier and scores
    - confidence and reviewer notes
  ↓
Build data/catalogue.json
  ↓
Build data/benchmarks.json
  ↓
Commit generated data to main
```

## LLM requirement

The final build requires `OPENAI_API_KEY` as a GitHub Actions secret. If the key is missing, the workflow fails early with a clear message instead of silently producing a weak mirror of the upstream lists.

Optional variable:

```text
OPENAI_MODEL
```

If not set, the script uses a compact default model configured in `scripts/extract_candidate_entry.py`.

## Duplicate handling

Records are merged only when strong keys match:

- same arXiv ID;
- same DOI;
- same normalized paper URL;
- same GitHub repository;
- same Hugging Face repository.

Weak name matches are reported separately in:

```text
data/candidates/*possible-duplicates.json
```

This avoids incorrect merging of different versions/releases.

## Benchmark/dataset extraction

Benchmark and dataset rows are separated from the model catalogue and written to:

```text
data/benchmarks.json
```

The public page is:

```text
benchmarks.html
```
