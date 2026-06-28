# Important: GitHub workflow folder

This repo contains the required hidden folder:

```text
.github/workflows/sync-upstreams.yml
```

GitHub Actions only works when the workflow file is at exactly that path.

Some systems hide folders that start with a dot. For convenience, this package also includes a visible copy:

```text
VISIBLE_GITHUB_FILES/workflows/sync-upstreams.yml
```

If you do not see `.github` after unzipping, do this on GitHub:

1. Code → Add file → Create new file
2. Name the file exactly:

```text
.github/workflows/sync-upstreams.yml
```

3. Copy the contents from:

```text
VISIBLE_GITHUB_FILES/workflows/sync-upstreams.yml
```

4. Commit directly to `main`.

The visible folder is only a backup/copy. The real workflow must be inside `.github/workflows/`.
