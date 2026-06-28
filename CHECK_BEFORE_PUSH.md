# Check before pushing

This repo includes the real GitHub Actions workflow at:

```text
.github/workflows/sync-upstreams.yml
```

On macOS Finder, press `Cmd + Shift + .` to show hidden folders and confirm `.github` is present.

Do not move `sync-upstreams.yml` to the repo root. GitHub Actions only runs it from `.github/workflows/`.

Required GitHub secret:

```text
OPENAI_API_KEY
```

Optional GitHub variable:

```text
OPENAI_MODEL
```

After pushing, check:

```text
GitHub repo → Actions → Build upstream-derived EO-FM catalogue
```
