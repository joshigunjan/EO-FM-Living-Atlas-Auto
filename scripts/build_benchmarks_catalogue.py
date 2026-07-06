from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import csv
from pathlib import Path

from entry_classification import classify_entry, has_benchmark_evidence, has_survey_evidence, source_evidence
from lib_utils import DATA, dump_json, load_json, slugify, strip_md
from public_fields import derive_category, derive_downstream_tasks, derive_modalities, derive_scope

CANDIDATE_PATHS = [
    DATA / "candidates" / "latest-candidates.extracted.json",
    DATA / "candidates" / "latest-candidates.with-metadata.json",
    DATA / "candidates" / "latest-candidates.json",
]
OUT_PATH = DATA / "benchmarks.json"
CSV_PATH = DATA / "benchmarks.csv"
META_PATH = DATA / "metadata.json"

FIELDNAMES = [
    "id", "name", "title", "resource_type", "benchmark_type", "scope", "tasks", "modalities", "paper_url", "code_url", "dataset_url", "project_url", "access", "source_names", "notes", "review_status",
]


def candidate_input_path() -> Path | None:
    for p in CANDIDATE_PATHS:
        if p.exists():
            return p
    return None


def unique(values):
    out = []
    for v in values:
        if isinstance(v, list):
            for x in v:
                if x and x not in out:
                    out.append(x)
        elif v and v not in out:
            out.append(v)
    return out


def is_benchmark_like(c: dict) -> bool:
    if c.get("resource_type") in {"benchmark", "dataset", "benchmark_dataset"}:
        return True
    text = " ".join(str(c.get(k, "")) for k in ["name", "title", "category", "scope", "downstream_tasks"]).lower()
    if any(token in text for token in ["benchmark", "-bench", " bench", "dataset", "evaluation suite"]):
        return True
    for ev in c.get("source_evidence", []) or []:
        section = str(ev.get("section", "")).lower()
        rt = str(ev.get("resource_type", "")).lower()
        if rt in {"benchmark", "dataset", "benchmark_dataset"}:
            return True
        if any(w in section for w in ["benchmark", "dataset", "pre-training", "pretraining", "embeddings data"]):
            return True
    return False


def infer_type(c: dict) -> str:
    category = derive_category(c, "benchmark")
    if category in {"Benchmark", "Dataset", "Pre-training dataset", "Embedding dataset"}:
        return category
    text = " ".join(str(c.get(k, "")) for k in ["name", "title", "category", "scope"]).lower()
    sections = " ".join(str(ev.get("section", "")) for ev in c.get("source_evidence", []) or []).lower()
    if "pre-training" in sections or "pretraining" in sections:
        return "Pre-training dataset"
    if "embedding" in sections:
        return "Embedding dataset"
    if "benchmark" in sections or "bench" in text:
        return "Benchmark"
    if "dataset" in sections or "dataset" in text:
        return "Dataset"
    return "Benchmark / dataset"


def pick_task_text(c: dict) -> str:
    # Prefer explicit task-like columns from upstream rows.
    values = []
    for rec in c.get("source_records", []) or []:
        cols = rec.get("raw_columns", {}) if isinstance(rec, dict) else {}
        for key, val in cols.items():
            lk = str(key).lower()
            if any(w in lk for w in ["task", "tasks", "attribute", "evaluation", "application"]):
                clean = strip_md(str(val))
                if clean:
                    values.append(clean)
    if values:
        return "; ".join(unique(values))
    return derive_downstream_tasks(c, "benchmark")


def source_names(c: dict) -> list[str]:
    names = []
    for ev in c.get("source_evidence", []) or []:
        name = ev.get("source_name") if isinstance(ev, dict) else ""
        if name and name not in names:
            names.append(name)
    return names


def url_from_candidate(c: dict) -> str:
    # Dataset/project links often enter via code_url/project_url depending on upstream column names.
    return c.get("weights_url") or c.get("project_url") or c.get("code_url") or ""


def benchmark_identity(c: dict) -> tuple[str, str]:
    for ev in source_evidence(c):
        section = str(ev.get("section") or "").lower()
        rt = str(ev.get("resource_type") or "").lower()
        if rt in {"benchmark", "dataset", "benchmark_dataset"} or any(w in section for w in ["benchmark", "dataset", "pre-training", "pretraining", "embeddings data"]):
            name = strip_md(str(ev.get("detected_name") or "")).strip()
            title = strip_md(str(ev.get("detected_title") or "")).strip()
            if name or title:
                return name or title, title or name
    name = (c.get("name") or c.get("title") or "Unnamed benchmark").strip()
    title = (c.get("title") or name).strip()
    return name, title


def to_benchmark(c: dict, used_ids: Counter) -> dict:
    name, title = benchmark_identity(c)
    base_id = slugify(name or c.get("id") or "benchmark", fallback="benchmark")
    used_ids[base_id] += 1
    entry_id = base_id if used_ids[base_id] == 1 else f"{base_id}-{used_ids[base_id]}"
    tasks = pick_task_text(c)
    modalities = ", ".join(derive_modalities(c)) or "—"
    return {
        "id": entry_id,
        "name": name,
        "title": title,
        "resource_type": "benchmark_dataset",
        "entry_type": "benchmark_dataset",
        "entry_type_reason": c.get("entry_type_reason") or "",
        "benchmark_type": infer_type(c),
        "scope": derive_scope(c, "benchmark"),
        "tasks": tasks,
        "modalities": modalities,
        "paper_url": c.get("paper_url") or "",
        "code_url": c.get("code_url") or "",
        "dataset_url": url_from_candidate(c),
        "project_url": c.get("project_url") or "",
        "access": c.get("access_label") or c.get("openness_label") or c.get("access") or c.get("openness") or "Unknown",
        "source_names": source_names(c),
        "source_evidence": c.get("source_evidence") or [],
        "deduplication_keys": c.get("deduplication_keys") or [],
        "conflicts": c.get("conflicts") or [],
        "notes": c.get("notes_for_reviewer") or "Auto-generated from upstream benchmark/dataset sections; review before treating as verified.",
        "review_status": c.get("review_status") or "upstream_auto",
        "needs_review": True,
    }


def write_csv(entries: list[dict]) -> None:
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for e in entries:
            row = {}
            for k in FIELDNAMES:
                v = e.get(k)
                if isinstance(v, (list, dict)):
                    row[k] = str(v)
                elif v is None:
                    row[k] = ""
                else:
                    row[k] = v
            writer.writerow(row)


def is_benchmark_candidate(c: dict) -> bool:
    """Return True if the candidate should appear in the benchmark catalogue.

    Uses LLM entry_type first (set by extract_candidate_entry.py or propagated
    from build_upstream_catalogue.py via _resolved_entry_type), then falls back
    to pre_classified_type, resource_type, and the existing heuristic.
    """
    et, reason = classify_entry(c)
    c["entry_type"] = et
    c["entry_type_reason"] = c.get("entry_type_reason") or reason
    if et == "benchmark_dataset":
        return True
    if et in {"survey_review", "paper_method", "unknown"}:
        return False

    # Some papers introduce both a model and a named benchmark/dataset. Keep the
    # model in catalogue.json and expose the benchmark evidence here too.
    if et == "model" and has_benchmark_evidence(c) and not has_survey_evidence(c):
        return True

    # resource_type fallback (set by detect_new_entries.py before LLM step).
    rt = str(c.get("resource_type") or "").strip()
    if rt in {"benchmark", "dataset", "benchmark_dataset"}:
        return True
    if rt == "model":
        return False

    return is_benchmark_like(c)


def main() -> int:
    path = candidate_input_path()
    if not path:
        print("No candidate file found; leaving benchmarks unchanged.")
        return 0
    candidates = load_json(path, [])
    bench_candidates = [c for c in candidates if is_benchmark_candidate(c)]
    used_ids: Counter = Counter()
    entries = [to_benchmark(c, used_ids) for c in bench_candidates]
    entries.sort(key=lambda e: (e.get("benchmark_type", ""), e.get("name", "").lower()))
    dump_json(OUT_PATH, entries)
    write_csv(entries)
    metadata = load_json(META_PATH, {}) or {}
    metadata.update({
        "benchmark_dataset_count": len(entries),
        "benchmark_dataset_source": "Generated from upstream benchmark/dataset sections and LLM entry_type=benchmark_dataset classifications.",
        "benchmarks_generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    })
    dump_json(META_PATH, metadata)
    print(f"Wrote {len(entries)} benchmark/dataset entries to {OUT_PATH}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
