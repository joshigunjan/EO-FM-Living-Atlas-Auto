from __future__ import annotations

import sys
from pathlib import Path

import requests

from lib_utils import DATA, dump_json, load_json, now_utc, sha256_text, slugify

SOURCES_PATH = DATA / "upstream_sources.json"
RAW_DIR = DATA / "upstream_raw"
SNAPSHOT_CURRENT = DATA / "upstream_snapshot.current.json"


def raw_url_for(source: dict) -> str:
    if source.get("raw_url"):
        return source["raw_url"]
    repo = source["repo"]
    branch = source.get("branch", "main")
    file = source.get("file", "README.md")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{file}"


def main() -> int:
    sources = load_json(SOURCES_PATH, [])
    if not sources:
        print("No upstream sources configured.")
        return 1

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = {"fetched_at": now_utc(), "sources": {}}
    failures = []

    for source in sources:
        sid = source.get("id") or slugify(source.get("name") or source.get("repo"))
        url = raw_url_for(source)
        print(f"Fetching {sid}: {url}")
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": "EO-FM-Living-Atlas-Auto/1.0"})
            r.raise_for_status()
            text = r.text
            (RAW_DIR / f"{sid}.md").write_text(text, encoding="utf-8")
            snapshot["sources"][sid] = {
                "name": source.get("name", sid),
                "repo": source.get("repo", ""),
                "url": url,
                "file": source.get("file", "README.md"),
                "priority": source.get("priority", "medium"),
                "sha256": sha256_text(text),
                "line_count": len(text.splitlines()),
                "status": "ok",
            }
        except Exception as exc:  # keep the sync useful even if one source fails
            print(f"WARNING: failed to fetch {sid}: {exc}", file=sys.stderr)
            snapshot["sources"][sid] = {
                "name": source.get("name", sid),
                "repo": source.get("repo", ""),
                "url": url,
                "priority": source.get("priority", "medium"),
                "status": "failed",
                "error": str(exc),
            }
            failures.append(sid)

    dump_json(SNAPSHOT_CURRENT, snapshot)
    print(f"Fetched {len(snapshot['sources']) - len(failures)} sources; {len(failures)} failures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
