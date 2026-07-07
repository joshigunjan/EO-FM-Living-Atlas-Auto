# Install the semantic Paper map

From the root of `EO-FM-Living-Atlas-Auto`:

```bash
unzip -o eo-fm-paper-map-patch.zip
python3 scripts/integrate_paper_map.py

git add \
  paper-map.html \
  paper-map.js \
  scripts/build_paper_map.py \
  scripts/integrate_paper_map.py \
  .github/workflows/build-paper-map.yml \
  .github/workflows/sync-upstreams.yml \
  .gitignore \
  index.html landscape.html benchmarks.html submit.html method.html README.md

git commit -m "add semantic abstract paper map"
git push origin main
```

The existing `OPENAI_API_KEY` secret is reused. The default embedding model is
`text-embedding-3-small`. You can override it with the repository variable
`EMBEDDING_MODEL`.

After the normal catalogue workflow completes, the new **Build semantic paper
map** workflow retrieves abstracts, creates embeddings, clusters the papers,
generates `data/paper-map.json`, and commits it to `main`.
