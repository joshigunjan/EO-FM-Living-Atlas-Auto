from __future__ import annotations

import subprocess
from datetime import datetime, timezone


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print("$", " ".join(cmd))
    return subprocess.run(cmd, check=check, text=True)


def main() -> int:
    run(["git", "config", "user.name", "github-actions[bot]"])
    run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
    run(["git", "add", "data/catalogue.json", "data/catalogue.csv", "data/benchmarks.json", "data/benchmarks.csv", "data/metadata.json", "data/candidates", "data/parsed", "data/upstream_raw", "data/upstream_snapshot.json"], check=False)
    status = subprocess.run(["git", "status", "--porcelain"], text=True, capture_output=True, check=True).stdout.strip()
    if not status:
        print("No generated catalogue changes to commit.")
        return 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run(["git", "commit", "-m", f"Refresh upstream-derived catalogue ({today})"])
    run(["git", "pull", "--rebase", "origin", "main"], check=False)
    run(["git", "push"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
