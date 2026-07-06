from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from entry_classification import (
    MODEL_ENTRY_TYPES,
    NON_MODEL_ENTRY_TYPES,
    best_model_name,
    classify_entry,
    public_model_id,
)
from public_fields import (
    derive_architectures,
    derive_category,
    derive_downstream_tasks,
    derive_evaluation_count,
    derive_modalities,
    derive_scope,
    derive_task_tags,
    clean_text,
    is_placeholder,
    landscape_score,
)
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
SUPPLEMENT_PATH = DATA / "supplemental_catalogue.json"
REPORT_PATH = DATA / "candidates" / "publication-report.json"

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



BAD_MODEL_NAMES_PUBLIC = {"", "-", "—", "–", "n/a", "na", "none", "unknown", "entry", "unnamed candidate", "unnamed entry"}

PAPER_TITLE_STARTS = (
    "a ", "an ", "the ", "towards ", "toward ",
    "a review", "review of", "survey of", "a survey",
    "a genealogy", "challenges and applications",
    "self-supervised learning of", "self-supervised vision transformers for",
)


def _clean_public_name(value: str) -> str:
    value = str(value or "").strip()
    if value.lower() in BAD_MODEL_NAMES_PUBLIC:
        return ""
    return value


def _url_tail_name(url: str) -> str:
    url = str(url or "").split("?")[0].rstrip("/")
    if not url:
        return ""
    parts = [p for p in url.split("/") if p]
    lower = url.lower()
    if ("github.com" in lower or "huggingface.co" in lower) and len(parts) >= 2:
        return _clean_public_name(parts[-1])
    return ""


def _title_prefix_name(title: str) -> str:
    title = str(title or "").strip()
    if ":" not in title:
        return ""
    prefix = _clean_public_name(title.split(":", 1)[0])
    if not prefix:
        return ""
    low = prefix.lower()
    if low.startswith(("a ", "an ", "the ", "towards ", "toward ", "review ", "survey ")):
        return ""
    if len(prefix.split()) > 5 or len(prefix) > 45:
        return ""
    return prefix


def _looks_like_paper_title(name: str) -> bool:
    n = str(name or "").strip()
    low = n.lower()
    normalized = low.replace("-", " ").replace("_", " ")
    words = normalized.split()

    bad_phrases = [
        "agentic ai in remote sensing",
        "brain inspired remote sensing foundation models",
        "foundation models and open problems",
        "open problems",
        "genealogy of foundation models",
        "charting new territories",
        "awesome geospatial",
        "awesome remote sensing",
        "survey of",
        "a survey",
        "review of",
        "a review",
        "taxonomy",
        "foundations taxonomy",
        "challenges and applications",
    ]

    if any(phrase in normalized for phrase in bad_phrases):
        return True

    if low.startswith(("a review", "review ", "survey ", "a survey", "towards ", "toward ")):
        return True

    if low.startswith(("awesome-", "awesome_", "awesome ")):
        return True

    # Long sentence-like names are usually paper titles.
    # Do not reject compact model names like A2-MAE, Prithvi-EO, SatMAE, Clay, AnySat.
    if len(words) >= 6:
        return True

    return False


def _has_model_like_name(name: str) -> bool:
    n = _clean_public_name(name)
    if not n:
        return False
    if _looks_like_paper_title(n):
        return False

    # Compact names are usually real model/framework names.
    # Examples: A2-MAE, AgriFM, AnySat, Clay, SatMAE, Prithvi-EO.
    if " " not in n and 2 <= len(n) <= 60:
        return True

    # Allow very short phrase names such as "Change-Agent" after normalization.
    if len(n.replace("-", " ").replace("_", " ").split()) <= 3:
        return True

    return False


def is_paper_only_candidate(c: dict) -> bool:
    name = str(c.get("name") or "")
    title = str(c.get("title") or "")
    category = str(c.get("category") or "")
    scope = str(c.get("scope") or "")

    text = " ".join([name, title, category, scope]).lower()
    normalized = text.replace("-", " ").replace("_", " ")

    sections = []
    for ev in c.get("source_evidence", []) or []:
        if isinstance(ev, dict):
            sections.append(str(ev.get("section") or "").lower())
    section_text = " ".join(sections)

    # These sections are not model catalogues.
    if any(x in section_text for x in ["survey", "commentary", "review"]):
        return True

    bad_text = [
        "survey",
        "review",
        "commentary",
        "taxonomy",
        "open problems",
        "genealogy",
        "charting new territories",
        "awesome geospatial",
        "awesome remote sensing",
        "foundations taxonomy",
    ]

    if any(x in normalized for x in bad_text):
        return True

    if _looks_like_paper_title(name):
        return True

    has_model_link = bool(c.get("code_url") or c.get("weights_url") or c.get("project_url"))

    # If there is no model/code/project link, require a compact model-like name.
    if not has_model_link and not _has_model_like_name(name):
        return True

    return False

def is_paper_only_candidate(c: dict) -> bool:
    name = str(c.get("name") or "")
    title = str(c.get("title") or "")
    category = str(c.get("category") or "")
    scope = str(c.get("scope") or "")

    text = " ".join([name, title, category, scope]).lower()
    normalized = text.replace("-", " ").replace("_", " ")

    sections = []
    for ev in c.get("source_evidence", []) or []:
        if isinstance(ev, dict):
            sections.append(str(ev.get("section") or "").lower())

    section_text = " ".join(sections)

    # Entire sections that are not model catalogues.
    if any(x in section_text for x in ["survey", "commentary", "review"]):
        return True

    bad_text = [
        "survey",
        "review",
        "commentary",
        "taxonomy",
        "open problems",
        "genealogy",
        "charting new territories",
        "awesome geospatial",
        "awesome remote sensing",
        "foundations taxonomy",
    ]

    if any(x in normalized for x in bad_text):
        return True

    # No code/weights/project + long prose-like name = likely paper-only row.
    has_model_link = bool(c.get("code_url") or c.get("weights_url") or c.get("project_url"))
    if not has_model_link and len(name.replace("-", " ").split()) >= 5:
        return True

    return False

def choose_public_model_name(c: dict) -> str:
    if is_paper_only_candidate(c):
        return ""
    candidates = []

    candidates.append(c.get("name", ""))

    for alias in c.get("aliases", []) or []:
        candidates.append(alias)

    for field in ["code_url", "weights_url", "project_url"]:
        candidates.append(_url_tail_name(c.get(field, "")))

    candidates.append(_title_prefix_name(c.get("title", "")))

    for ev in c.get("source_evidence", []) or []:
        if isinstance(ev, dict):
            candidates.append(ev.get("detected_name", ""))

    for name in candidates:
        name = _clean_public_name(name)
        if not name:
            continue
        if _looks_like_paper_title(name):
            continue
        return name

    return ""


def to_catalogue_entry(c: dict, used_ids: Counter) -> dict:
    title = (c.get("title") or c.get("name") or "").strip()
    name = (best_model_name(c) or c.get("name") or title.split(":", 1)[0] or "Unnamed entry").strip()
    category = derive_category(c, "model")
    source_evidence = c.get("source_evidence") or []
    source_records = c.get("source_records") or []
    public_scope = derive_scope(c, "model")
    public_tasks = derive_downstream_tasks(c, "model")
    public_task_tags = derive_task_tags(c)
    public_modality_tags = derive_modalities(c)
    public_architecture_tags = derive_architectures(c)
    public_eval_count = derive_evaluation_count(c)
    public_landscape_score = landscape_score(c)
    raw_text = " ".join([
        name,
        title,
        category,
        public_scope,
        c.get("input_modality", ""),
        c.get("architecture", ""),
        public_tasks,
        " ".join(str(r.get("raw_row", "")) for r in source_records if isinstance(r, dict)),
    ])

    modality_tags = public_modality_tags or as_list(c.get("modality_tags")) or infer_modality_tags(raw_text)
    architecture_tags = public_architecture_tags or as_list(c.get("architecture_tags")) or infer_architecture_tags(raw_text)
    architecture = clean_text(c.get("architecture"))
    if is_placeholder(architecture):
        architecture = "; ".join(architecture_tags) if architecture_tags else "—"
    architecture = architecture.replace("Contrastive; Contrastive / CLIP", "Contrastive / CLIP")
    training_scale = clean_text(c.get("training_scale"))
    if is_placeholder(training_scale):
        training_scale = "—"
    access, access_label = normalize_access(c)
    stage_key, stage_label, stage_score = stage_from_candidate(c, modality_tags, category, raw_text)
    paradigm_key, paradigm_label = paradigm_from_candidate(c, architecture_tags, category, raw_text)

    base_id = public_model_id(c) or slugify(c.get("id") or name)
    used_ids[base_id] += 1
    entry_id = base_id if used_ids[base_id] == 1 else f"{base_id}-{used_ids[base_id]}"

    notes = c.get("notes")
    if is_placeholder(notes) or "verify" in clean_text(notes).lower():
        notes = "Auto-derived from upstream source evidence; primary links are retained for traceability."
    src_names = []
    for ev in source_evidence:
        if isinstance(ev, dict) and ev.get("source_name") and ev.get("source_name") not in src_names:
            src_names.append(ev.get("source_name"))

    return {
        "id": entry_id,
        "name": name,
        "title": title,
        "scope": public_scope,
        "category": category,
        "input_modality": ", ".join(modality_tags) if modality_tags else "—",
        "modality_tags": modality_tags,
        "architecture": architecture,
        "architecture_tags": architecture_tags,
        "modelling_paradigm_key": paradigm_key,
        "modelling_paradigm": paradigm_label,
        "downstream_tasks": public_tasks,
        "task_tags": public_task_tags,
        "training_scale": training_scale,
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
        "reported_downstream_task_count": public_eval_count,
        "reported_downstream_task_count_basis": "reported_or_inferred_from_upstream_evidence" if public_eval_count else "not_reported_by_upstream_source",
        "landscape_score": public_landscape_score,
        "fm_strength": c.get("fm_strength") if not is_placeholder(c.get("fm_strength")) else "Upstream-listed model",
        "notes": notes,
        "review_status": "upstream_auto",
        "needs_review": True,
        "entry_type": c.get("entry_type") or "model",
        "entry_type_reason": c.get("entry_type_reason") or "",
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
        if field == "code_url" and entry.get("allow_shared_code_repo"):
            continue
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


# entry_type values that should appear in the main model catalogue.
_MODEL_ENTRY_TYPES = MODEL_ENTRY_TYPES

# entry_type values that should be silently excluded from the model catalogue
# (they will be handled by build_benchmarks_catalogue.py or ignored).
_NON_MODEL_ENTRY_TYPES = NON_MODEL_ENTRY_TYPES


def classify_candidate(c: dict) -> str:
    """Return the best available entry_type for a candidate.

    Priority: LLM-assigned entry_type → pre_classified_type → resource_type + heuristic fallback.

    On the first pipeline run after this change, LLM entry_type and pre_classified_type
    will not be present in legacy extracted files — in that case the function falls back to
    resource_type (set by detect_new_entries.py) then is_benchmark_like.
    After the next full pipeline run, LLM entry_type is the primary signal for every entry.
    """
    entry_type, reason = classify_entry(c)
    c["entry_type"] = entry_type
    c["entry_type_reason"] = c.get("entry_type_reason") or reason
    return entry_type


def normalize_supplement_entry(entry: dict, used_ids: Counter) -> dict:
    candidate = dict(entry)
    candidate.setdefault("entry_type", "model")
    candidate.setdefault("entry_type_reason", "Curated supplemental entry from primary public sources.")
    candidate.setdefault("review_status", "curated_supplement")
    candidate.setdefault("needs_review", False)
    candidate.setdefault("extraction_confidence", "high")
    candidate.setdefault("extraction_method", "curated_supplement")
    candidate.setdefault("source_names", ["Curated supplement"])
    base_id = slugify(candidate.get("id") or candidate.get("name") or "supplement", fallback="supplement")
    used_ids[base_id] += 1
    candidate["id"] = base_id if used_ids[base_id] == 1 else f"{base_id}-{used_ids[base_id]}"
    candidate.setdefault("openness_text", candidate.get("openness_label") or candidate.get("openness") or "Unknown")
    candidate.setdefault("reported_downstream_task_count_basis", "curated_from_primary_source")
    candidate.setdefault("landscape_score", landscape_score(candidate))
    return candidate


def main() -> int:
    path = candidate_input_path()
    if not path:
        print("No candidate file found; leaving catalogue unchanged.")
        return 0

    candidates = load_json(path, [])
    used_ids: Counter = Counter()

    # Classify every candidate using LLM entry_type where available, then
    # section pre-classification, then heuristic fallback.
    type_counts: Counter = Counter()
    model_candidates = []
    excluded = []
    for c in candidates:
        et = classify_candidate(c)
        c["_resolved_entry_type"] = et
        type_counts[et] += 1
        if et in _MODEL_ENTRY_TYPES and best_model_name(c):
            model_candidates.append(c)
        else:
            excluded.append({
                "id": c.get("id"),
                "name": c.get("name"),
                "title": c.get("title"),
                "entry_type": et,
                "entry_type_reason": c.get("entry_type_reason", ""),
                "publication_exclusion_reason": "missing_public_model_name" if et in _MODEL_ENTRY_TYPES else "non_model_entry_type",
                "paper_url": c.get("paper_url", ""),
                "code_url": c.get("code_url", ""),
            })

    supplement_entries = load_json(SUPPLEMENT_PATH, []) or []
    supplemental_public_entries = []
    for entry in supplement_entries:
        if isinstance(entry, dict):
            supplemental_public_entries.append(normalize_supplement_entry(entry, used_ids))
    auto_entries = [to_catalogue_entry(c, used_ids) for c in model_candidates]
    entries = merge_public_entries(supplemental_public_entries, auto_entries)
    entries.sort(key=lambda e: (e.get("category", ""), e.get("name", "").lower()))

    dump_json(OUT_PATH, entries)
    write_csv(entries)
    dump_json(REPORT_PATH, {
        "candidate_count": len(candidates),
        "published_model_count": len(entries),
        "excluded_count": len(excluded),
        "entry_type_distribution": dict(type_counts),
        "excluded": excluded,
        "note": "Only entry_type=model is published to data/catalogue.json. Benchmarks/datasets are written by build_benchmarks_catalogue.py; surveys and paper-only methods stay in data/candidates/.",
    })

    metadata = load_json(META_PATH, {}) or {}
    metadata.update({
        "catalogue_mode": "entry_type_classified_upstream_catalogue",
        "entry_count": len(entries),
        "auto_candidates_detected": len(candidates),
        "auto_model_entries_published": len(entries),
        "entry_type_distribution": dict(type_counts),
        "source": "Public catalogue generated automatically from upstream awesome-list sources. Entries are classified by the LLM (entry_type field) with section-based pre-classification as a fallback. Only 'model' entries appear here.",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "review_note": "Entries classified as survey_review, paper_method, benchmark_dataset, or unknown are excluded from this catalogue and kept only in data/candidates/.",
        "manual_seed_catalogue": str(SEED_PATH.relative_to(DATA.parent)) if SEED_PATH.exists() else "",
    })
    dump_json(META_PATH, metadata)

    print(f"Wrote classified public catalogue with {len(entries)} model entries.")
    print(f"Total auto candidates detected: {len(candidates)}")
    print(f"Entry-type distribution: {dict(type_counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
