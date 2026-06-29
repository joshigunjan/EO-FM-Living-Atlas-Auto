from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from lib_utils import DATA, dump_json, infer_access, infer_architecture_tags, infer_modality_tags, load_json, slugify

CANDIDATE_PATHS = [
    DATA / "candidates" / "latest-candidates.extracted.json",
    DATA / "candidates" / "latest-candidates.with-metadata.json",
    DATA / "candidates" / "latest-candidates.json",
]
OUT_PATH = DATA / "catalogue.json"
CSV_PATH = DATA / "catalogue.csv"
META_PATH = DATA / "metadata.json"
SEED_PATH = DATA / "manual_seed_catalogue.json"

FIELDNAMES = [
    "id", "name", "scope", "category", "input_modality", "modality_tags", "architecture", "architecture_tags",
    "modelling_paradigm_key", "modelling_paradigm", "downstream_tasks", "task_tags", "training_scale",
    "openness", "openness_label", "openness_text", "paper_url", "code_url", "weights_url", "project_url",
    "modality_complexity_tier_key", "modality_complexity_tier", "modality_complexity_score",
    "reported_downstream_task_count", "reported_downstream_task_count_basis", "fm_strength", "notes", "review_status",
]


def candidate_input_path() -> Path | None:
    for p in CANDIDATE_PATHS:
        if p.exists():
            return p
    return None


def as_list(value):
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [x.strip() for x in value.split(",") if x.strip()]
    return []


def normalize_access(c: dict) -> tuple[str, str]:
    access = c.get("access") or c.get("openness")
    label = c.get("access_label") or c.get("openness_label")
    if access and label:
        return access, label
    urls = [c.get(k, "") for k in ["paper_url", "code_url", "weights_url", "project_url"] if c.get(k)]
    inferred_access, inferred_label = infer_access(urls)
    return access or inferred_access, label or inferred_label


def stage_from_candidate(c: dict, modality_tags: list[str], category: str, text: str) -> tuple[str, str, float | None]:
    key = c.get("modality_complexity_tier_key") or ""
    label = c.get("modality_complexity_tier") or ""
    score = c.get("modality_complexity_score")
    if key and key != "needs_review" and label:
        try:
            return key, label, float(score) if score is not None else None
        except Exception:
            return key, label, None

    t = f"{category} {text}".lower()
    tags = {m.lower() for m in modality_tags}
    if "vision-language" in t or "language" in t or "mllm" in t or "llm" in t or "text" in tags:
        return "vision_language", "Vision-language / MLLM", 3
    if "generative" in t or "agent" in t or "any-to-any" in t or "generalist" in t:
        return "generalist", "Generalist models", 4
    if len(tags) > 1 or "multi" in t or "sar" in tags and ("multispectral" in tags or "optical" in tags):
        return "multi_modality", "Multi-modality encoders", 2
    if tags:
        return "single_modality", "Single-modality encoders", 1
    return "needs_review", "Needs review", None


def paradigm_from_candidate(c: dict, architecture_tags: list[str], category: str, text: str) -> tuple[str, str]:
    key = c.get("modelling_paradigm_key") or ""
    label = c.get("modelling_paradigm") or ""
    if key and key != "needs_review" and label:
        return key, label
    t = f"{category} {text}".lower()
    tags = {a.lower() for a in architecture_tags}
    if "vision-language" in t or "language" in t or "mllm" in t or "llm" in t or "vision-language" in tags:
        return "vision_language", "Vision-language / EO MLLM"
    if "generative" in t or "diffusion" in t or "any-to-any" in t or "generative" in tags:
        return "generative_hybrid", "Any-to-any generative / hybrid multimodal system"
    if "mamba" in t or "state-space" in t or "state space" in t or "state-space" in tags:
        return "state_space", "State-space / sequence model"
    if "clip" in t or "contrastive" in t or "contrastive" in tags:
        return "joint_embedding", "Joint-embedding / contrastive-predictive encoder"
    return "transformer_masked", "Transformer / masked-reconstruction encoder"


def is_benchmark_like(c: dict) -> bool:
    if c.get("resource_type") in {"benchmark", "dataset", "benchmark_dataset"}:
        return True
    text = " ".join(str(c.get(k, "")) for k in ["name", "title", "category", "scope"]).lower()
    if any(token in text for token in ["benchmark", "-bench", " bench", "dataset"]):
        return True
    for ev in c.get("source_evidence", []) or []:
        section = str(ev.get("section", "")).lower()
        rt = str(ev.get("resource_type", "")).lower()
        if rt in {"benchmark", "dataset", "benchmark_dataset"}:
            return True
        if any(w in section for w in ["benchmark", "dataset", "pre-training", "pretraining", "embeddings data"]):
            return True
    return False


def to_catalogue_entry(c: dict, used_ids: Counter) -> dict:
    title = (c.get("title") or c.get("name") or "").strip()
    name = (c.get("name") or title.split(":", 1)[0] or "Unnamed entry").strip()
    category = (c.get("category") or "Upstream-listed EO-FM entry").strip()
    source_evidence = c.get("source_evidence") or []
    if category == "Upstream candidate" and source_evidence:
        category = source_evidence[0].get("section") or category
    source_records = c.get("source_records") or []
    raw_text = " ".join([
        name,
        title,
        category,
        c.get("scope", ""),
        c.get("input_modality", ""),
        c.get("architecture", ""),
        c.get("downstream_tasks", ""),
        " ".join(str(r.get("raw_row", "")) for r in source_records if isinstance(r, dict)),
    ])

    modality_tags = as_list(c.get("modality_tags")) or infer_modality_tags(raw_text)
    architecture_tags = as_list(c.get("architecture_tags")) or infer_architecture_tags(raw_text)
    access, access_label = normalize_access(c)
    stage_key, stage_label, stage_score = stage_from_candidate(c, modality_tags, category, raw_text)
    paradigm_key, paradigm_label = paradigm_from_candidate(c, architecture_tags, category, raw_text)

    base_id = slugify(c.get("id") or name)
    used_ids[base_id] += 1
    entry_id = base_id if used_ids[base_id] == 1 else f"{base_id}-{used_ids[base_id]}"

    notes = c.get("notes_for_reviewer") or c.get("notes") or "Auto-generated from upstream awesome-list sources; review before treating as verified."
    src_names = []
    for ev in source_evidence:
        if isinstance(ev, dict) and ev.get("source_name") and ev.get("source_name") not in src_names:
            src_names.append(ev.get("source_name"))

    return {
        "id": entry_id,
        "name": name,
        "title": title,
        "scope": c.get("scope") or title or "Upstream-listed Earth observation foundation-model entry; details need curation.",
        "category": category,
        "input_modality": c.get("input_modality") or (", ".join(modality_tags) if modality_tags else "Needs review"),
        "modality_tags": modality_tags,
        "architecture": c.get("architecture") or "Needs review",
        "architecture_tags": architecture_tags,
        "modelling_paradigm_key": paradigm_key,
        "modelling_paradigm": paradigm_label,
        "downstream_tasks": c.get("downstream_tasks") or "Needs review",
        "task_tags": as_list(c.get("task_tags")),
        "training_scale": c.get("training_scale") or "Needs review",
        "openness": access,
        "openness_label": access_label,
        "openness_text": access_label,
        "paper_url": c.get("paper_url") or "",
        "code_url": c.get("code_url") or "",
        "weights_url": c.get("weights_url") or "",
        "project_url": c.get("project_url") or "",
        "modality_complexity_tier_key": stage_key,
        "modality_complexity_tier": stage_label,
        "modality_complexity_score": stage_score,
        "reported_downstream_task_count": c.get("reported_downstream_task_count"),
        "reported_downstream_task_count_basis": c.get("reported_downstream_task_count_basis") or "upstream_auto_not_verified",
        "fm_strength": c.get("fm_strength") or "Upstream-listed; needs curation",
        "notes": notes,
        "review_status": "upstream_auto",
        "needs_review": True,
        "extraction_confidence": c.get("extraction_confidence") or "low",
        "extraction_method": c.get("extraction_method") or "heuristic",
        "source_names": src_names,
        "source_evidence": source_evidence,
        "deduplication_keys": c.get("deduplication_keys") or [],
        "aliases": c.get("aliases") or [],
        "conflicts": c.get("conflicts") or [],
    }


def write_csv(entries: list[dict]) -> None:
    import csv
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


BAD_PUBLIC_NAMES = {"", "-", "—", "–", "n/a", "na", "none", "unknown", "unnamed candidate", "entry"}


def has_real_public_name(entry: dict) -> bool:
    name = str(entry.get("name") or "").strip()
    if name.lower() in BAD_PUBLIC_NAMES:
        return False
    if len(name) < 2:
        return False
    return True


def is_high_quality_auto_candidate(c: dict) -> bool:
    if not has_real_public_name(c):
        return False

    method = str(c.get("extraction_method") or "").lower()
    confidence = str(c.get("extraction_confidence") or "").lower()
    scope = str(c.get("scope") or "").strip()
    category = str(c.get("category") or "").strip()

    # Do not publish raw heuristic rows. Keep them only in data/candidates/.
    if method == "heuristic" or method.startswith("heuristic"):
        return False

    # Do not publish low-confidence LLM outputs.
    if confidence == "low":
        return False

    # Do not publish generic placeholder candidate text.
    if scope.startswith("Candidate Earth observation foundation model"):
        return False
    if category == "Candidate model entry":
        return False

    return True


def entry_keys(entry: dict) -> set[str]:
    keys = set()
    if entry.get("id"):
        keys.add("id:" + str(entry["id"]).lower())
    if entry.get("name"):
        keys.add("name:" + slugify(str(entry["name"])))
    for field in ["paper_url", "code_url", "weights_url", "project_url", "primary_source_url"]:
        value = str(entry.get(field) or "").strip().lower()
        if value:
            keys.add(field + ":" + value)
    return keys


def merge_public_entries(seed_entries: list[dict], auto_entries: list[dict]) -> list[dict]:
    out = []
    seen = set()

    for entry in seed_entries + auto_entries:
        keys = entry_keys(entry)
        if keys and keys & seen:
            continue
        out.append(entry)
        seen |= keys

    return out


def main() -> int:
    path = candidate_input_path()
    candidates = load_json(path, []) if path else []

    used_ids: Counter = Counter()

    # Fully automated public catalogue:
    # publish all upstream-derived model candidates.
    # Benchmark/dataset-like records are excluded here and written to data/benchmarks.json.
    model_candidates = [c for c in candidates if not is_benchmark_like(c)]

    entries = [to_catalogue_entry(c, used_ids) for c in model_candidates]
    entries.sort(key=lambda e: (e.get("category", ""), e.get("name", "").lower()))

    dump_json(OUT_PATH, entries)
    write_csv(entries)

    metadata = load_json(META_PATH, {}) or {}
    metadata.update({
        "catalogue_mode": "fully_automated_upstream_catalogue",
        "entry_count": len(entries),
        "auto_candidates_detected": len(candidates),
        "auto_model_entries_published": len(entries),
        "benchmark_dataset_count_excluded_from_model_catalogue": len(candidates) - len(model_candidates),
        "source": "Public catalogue is generated automatically from configured upstream awesome-list sources, then deduplicated, metadata-enriched, and LLM-normalized.",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "review_note": "Entries are automatically generated and should be treated as upstream-derived candidates unless manually verified.",
        "manual_seed_catalogue": str(SEED_PATH.relative_to(DATA.parent)) if SEED_PATH.exists() else "",
    })
    dump_json(META_PATH, metadata)

    print(f"Wrote fully automated public catalogue with {len(entries)} model entries.")
    print(f"Total auto candidates detected: {len(candidates)}")
    print(f"Benchmark/dataset entries excluded from model catalogue: {len(candidates) - len(model_candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
