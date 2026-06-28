# Deployment

1. Create a new GitHub repository, for example `EO-FM-Living-Atlas-Auto`.
2. Upload the contents of this folder to the repository root.
3. Add the OpenAI key as a GitHub Actions secret:

```text
Settings → Secrets and variables → Actions → Secrets → New repository secret
Name: OPENAI_API_KEY
Value: your OpenAI API key
```

4. Optional: set a model variable:

```text
Settings → Secrets and variables → Actions → Variables → New repository variable
Name: OPENAI_MODEL
Value: gpt-4o-mini
```

5. Go to `Settings → Pages`.
6. Set source to `Deploy from branch`.
7. Select branch `main`, folder `/root`.
8. Save.

## First run today

The workflow runs on push to `main`. Uploading/committing this repo triggers the first catalogue build immediately.

Check the run here:

```text
Repo → Actions → Build upstream-derived EO-FM catalogue
```

When it succeeds, it writes/updates:

```text
data/catalogue.json
data/benchmarks.json
data/metadata.json
data/candidates/latest-candidates.extracted.json
```

Then GitHub Pages updates the website.

## Regular schedule

After the first push run, the workflow runs automatically on:

```text
1st and 15th of every month at 04:17 UTC
```

## Important

Never put the OpenAI API key in code, README files, YAML files, issues, pull requests, or chat messages. Only use GitHub Actions secrets.
