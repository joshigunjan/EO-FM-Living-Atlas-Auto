from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from lib_utils import (
    DATA,
    dump_json,
    identity_keys,
    infer_access,
    infer_architecture_tags,
    infer_modality_tags,
    load_json,
    normalize_name,
    normalize_title,
    slugify,
    strip_md,
)

RECORDS_PATH = DATA / "parsed" / "upstream_records.json"
CATALOGUE_PATH = DATA / "catalogue.json"
SNAPSHOT_CURRENT = DATA / "upstream_snapshot.current.json"
CAND_DIR = DATA / "candidates"


class DSU:
    def __init__(self, n: int):
        self.parent = list(range(n))
    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x
    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def build_verified_keys(catalogue: list[dict]) -> set[str]:
    keys: set[str] = set()
    for entry in catalogue:
        for key in identity_keys(entry):
            keys.add(key)
        # exact normalized names are weaker, but useful to suppress obviously existing entries.
        if entry.get("name"):
            keys.add(f"verified_name:{normalize_name(entry['name'])}")
    return keys


def cluster_records(records: list[dict]) -> list[list[dict]]:
    dsu = DSU(len(records))
    key_to_idx: dict[str, int] = {}
    for i, rec in enumerate(records):
        keys = identity_keys(rec)
        # Strong keys: paper/code/weights/project identities. No fuzzy version merging here.
        for key in keys:
            if key in key_to_idx:
                dsu.union(i, key_to_idx[key])
            else:
                key_to_idx[key] = i
    groups = defaultdict(list)
    for i, rec in enumerate(records):
        groups[dsu.find(i)].append(rec)
    return list(groups.values())


BAD_MODEL_NAMES = {"", "-", "—", "–", "n/a", "na", "none", "unknown", "entry", "unnamed candidate"}


def clean_name_value(value: str) -> str:
    value = strip_md(value or "").strip()
    if value.lower() in BAD_MODEL_NAMES:
        return ""
    return value


def name_from_url(url: str) -> str:
    url = (url or "").split("?")[0].rstrip("/")
    if not url:
        return ""
    parts = [p for p in url.split("/") if p]
    lower = url.lower()

    if "github.com" in lower and len(parts) >= 2:
        return clean_name_value(parts[-1])
    if "huggingface.co" in lower and len(parts) >= 2:
        return clean_name_value(parts[-1])

    return ""


def choose_first(values: list[str]) -> str:
    vals = [clean_name_value(v) for v in values]
    vals = [v for v in vals if v]
    if not vals:
        return ""

    # Prefer compact repo/model names over long paper titles.
    vals = sorted(vals, key=lambda x: (len(x) > 60, len(x)))
    return vals[0]


def unique(values: list[str]) -> list[str]:
    out = []
    for v in values:
        v = v or ""
        if v and v not in out:
            out.append(v)
    return out



BAD_MODEL_NAMES = {"", "-", "—", "–", "n/a", "na", "none", "unknown", "entry", "unnamed candidate"}


def clean_name_value(value: str) -> str:
    value = strip_md(value or "").strip()
    if value.lower() in BAD_MODEL_NAMES:
        return ""
    return value


def name_from_url(url: str) -> str:
    url = (url or "").split("?")[0].rstrip("/")
    if not url:
        return ""
    parts = [x for x in url.split("/") if x]
    lower = url.lower()
    if "github.com" in lower and len(parts) >= 2:
        return clean_name_value(parts[-1])
    if "huggingface.co" in lower and len(parts) >= 2:
        return clean_name_value(parts[-1])
    return ""


def name_from_title(title: str) -> str:
    title = strip_md(title or "").strip()
    if ":" not in title:
        return ""
    prefix = clean_name_value(title.split(":", 1)[0])
    if not prefix:
        return ""
    low = prefix.lower()
    if low.startswith(("a ", "an ", "the ", "towards ", "toward ", "review ", "survey ")):
        return ""
    if len(prefix.split()) > 5 or len(prefix) > 45:
        return ""
    return prefix


def make_candidate(group: list[dict], sync_date: str) -> dict:
    names = unique([r.get("name", "") for r in group])
    titles = unique([r.get("title", "") for r in group])
    paper_urls = unique([r.get("paper_url", "") for r in group])
    code_urls = unique([r.get("code_url", "") for r in group])
    weights_urls = unique([r.get("weights_url", "") for r in group])
    project_urls = unique([r.get("project_url", "") for r in group])
    all_urls = unique([u for r in group for u in r.get("all_urls", [])])

    url_names = [name_from_url(u) for u in (code_urls + weights_urls + project_urls)]
    title_names = [name_from_title(t) for t in titles]
    name = choose_first(names) or choose_first(url_names) or choose_first(title_names) or "Unnamed candidate"
    title = choose_first(titles) or name
    text_blob = "\n".join([name, title] + [r.get("raw_row", "") for r in group])
    modality_tags = infer_modality_tags(text_blob)
    architecture_tags = infer_architecture_tags(text_blob)
    access, access_label = infer_access(all_urls + paper_urls + code_urls + weights_urls + project_urls)

    conflicts = []
    for field, vals in [("paper_url", paper_urls), ("code_url", code_urls), ("weights_url", weights_urls), ("project_url", project_urls)]:
        nonempty = unique([v for v in vals if v])
        if len(nonempty) > 1:
            conflicts.append({"field": field, "values": nonempty, "note": "Multiple upstream values detected; reviewer should choose canonical link."})

    keys = []
    for rec in group:
        for k in identity_keys(rec):
            if k not in keys:
                keys.append(k)

    aliases = unique([v for v in names if v and normalize_name(v) != normalize_name(name)])
    source_evidence = []
    for rec in group:
        source_evidence.append({
            "source_id": rec.get("source_id"),
            "source_name": rec.get("source_name"),
            "source_repo": rec.get("source_repo"),
            "detected_name": rec.get("name"),
            "detected_title": rec.get("title"),
            "section": rec.get("section"),
            "resource_type": rec.get("resource_type", "model"),
            "paper_url": rec.get("paper_url"),
            "code_url": rec.get("code_url"),
            "weights_url": rec.get("weights_url"),
            "project_url": rec.get("project_url"),
        })

    resource_types = unique([r.get("resource_type", "") for r in group])
    is_benchmark_or_dataset = any(rt in {"benchmark", "dataset", "benchmark_dataset"} for rt in resource_types)
    default_scope = "Candidate benchmark dataset or evaluation resource for Earth observation foundation models. Needs curator review." if is_benchmark_or_dataset else "Candidate Earth observation foundation model or related resource. Needs curator review."
    default_category = "Benchmark / dataset candidate" if is_benchmark_or_dataset else "Candidate model entry"

    return {
        "id": slugify(name),
        "name": name,
        "title": title,
        "resource_type": "benchmark_dataset" if is_benchmark_or_dataset else "model",
        "scope": default_scope,
        "category": default_category,
        "input_modality": ", ".join(modality_tags),
        "modality_tags": modality_tags,
        "architecture": "To be verified from the primary paper or project page.",
        "architecture_tags": architecture_tags,
        "modelling_paradigm_key": "needs_review",
        "modelling_paradigm": "Needs review",
        "downstream_tasks": "To be verified from the primary paper or benchmark description.",
        "task_tags": [],
        "training_scale": "To be verified.",
        "access": access,
        "access_label": access_label,
        "paper_url": paper_urls[0] if paper_urls else "",
        "code_url": code_urls[0] if code_urls else "",
        "weights_url": weights_urls[0] if weights_urls else "",
        "project_url": project_urls[0] if project_urls else "",
        "modality_complexity_tier_key": "needs_review",
        "modality_complexity_tier": "Needs review",
        "modality_complexity_score": None,
        "reported_downstream_task_count": None,
        "reported_downstream_task_count_basis": "candidate_not_verified",
        "extraction_confidence": "low",
        "needs_review": True,
        "review_status": "candidate",
        "sync_detected_at": sync_date,
        "source_records": group,
        "source_evidence": source_evidence,
        "deduplication_keys": keys,
        "aliases": aliases,
        "conflicts": conflicts,
        "notes_for_reviewer": "Auto-detected from upstream lists. Verify against original paper/code/weights before moving to data/catalogue.json.",
    }


def main() -> int:
    records = load_json(RECORDS_PATH, [])
    catalogue = load_json(CATALOGUE_PATH, [])
    snapshot = load_json(SNAPSHOT_CURRENT, {})
    sync_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    CAND_DIR.mkdir(parents=True, exist_ok=True)

    verified_keys = build_verified_keys(catalogue)
    groups = cluster_records(records)
    candidates = []
    matched_existing = []
    weak_name_groups = defaultdict(list)

    for group in groups:
        cand = make_candidate(group, sync_date)
        group_keys = set(cand.get("deduplication_keys", []))
        weak_name = normalize_name(cand.get("name", ""))
        # Full automated rebuild mode:
        # keep every upstream-derived cluster in latest-candidates.json.
        # Do not suppress entries just because they match the previous public catalogue.
        if group_keys & verified_keys or (weak_name and f"verified_name:{weak_name}" in verified_keys):
            matched_existing.append({
                "matched_candidate_name": cand.get("name"),
                "deduplication_keys": sorted(group_keys & verified_keys),
                "source_evidence": cand.get("source_evidence", []),
            })
        candidates.append(cand)
        if weak_name:
            weak_name_groups[weak_name].append(cand)

    possible_duplicates = []
    for weak_name, entries in weak_name_groups.items():
        if len(entries) > 1:
            possible_duplicates.append({
                "normalized_name": weak_name,
                "entries": [{"id": e["id"], "name": e["name"], "paper_url": e.get("paper_url"), "code_url": e.get("code_url")} for e in entries],
                "note": "Same normalized name but not merged by strong key. Review manually; this may be different versions/releases.",
            })

    dated = CAND_DIR / f"{sync_date}-candidates.json"
    latest = CAND_DIR / "latest-candidates.json"
    dump_json(dated, candidates)
    dump_json(latest, candidates)
    dump_json(CAND_DIR / f"{sync_date}-matched-existing.json", matched_existing)
    dump_json(CAND_DIR / f"{sync_date}-possible-duplicates.json", possible_duplicates)
    dump_json(DATA / "upstream_snapshot.json", snapshot)

    print(f"Strong-deduplicated raw records into {len(groups)} clusters.")
    print(f"New candidate clusters: {len(candidates)}")
    print(f"Matched existing catalogue: {len(matched_existing)}")
    print(f"Possible weak duplicates for review: {len(possible_duplicates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
