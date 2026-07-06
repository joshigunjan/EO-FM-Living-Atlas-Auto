from __future__ import annotations

import re

from lib_utils import infer_architecture_tags, infer_modality_tags, strip_md

PLACEHOLDER_PATTERNS = (
    "candidate earth observation foundation model",
    "candidate benchmark dataset",
    "needs curator review",
    "needs review",
    "to be verified",
    "candidate_not_verified",
)

TASK_PATTERNS = [
    ("semantic segmentation", ("semantic segmentation", "segmentation", "segment anything")),
    ("scene classification", ("scene classification", "image classification", "classification", "classifying")),
    ("object detection", ("object detection", "detection", "detecting")),
    ("change detection", ("change detection", "building/change", "change mapping")),
    ("land-cover mapping", ("land cover", "land-cover", "land-use", "lulc")),
    ("crop mapping", ("crop", "agriculture", "agricultural", "farm", "plantation")),
    ("forest monitoring", ("forest", "tree canopy", "biomass")),
    ("flood mapping", ("flood", "water-body", "water body", "marine debris", "oil-spill", "oil spill")),
    ("burn-scar mapping", ("wildfire", "burn scar", "burn-scar", "fire")),
    ("visual question answering", ("visual question answering", "vqa", "question answering")),
    ("captioning", ("caption", "image-text", "image text")),
    ("image-text retrieval", ("retrieval", "matching", "alignment", "contrastive")),
    ("geolocation", ("geolocation", "geolocalization", "location recognition", "geographic")),
    ("counting", ("counting", "count")),
    ("regression", ("regression", "estimation", "predicting", "forecasting")),
    ("super-resolution", ("super-resolution", "super resolution")),
    ("generation", ("generation", "generative", "text-driven", "text to image", "text-to-image", "diffusion")),
    ("time-series forecasting", ("time series", "time-series", "temporal", "spatiotemporal")),
    ("agentic reasoning", ("agent", "tool-augmented", "planning", "reasoning")),
]


def clean_text(value: object) -> str:
    text = strip_md(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip(" .;:-\n\t")
    return text


def is_placeholder(value: object) -> bool:
    text = clean_text(value).lower()
    return not text or any(pattern in text for pattern in PLACEHOLDER_PATTERNS)


def public_title(candidate: dict) -> str:
    title = clean_text(candidate.get("title"))
    name = clean_text(candidate.get("name"))
    if title and title.lower() != name.lower():
        return title
    for rec in candidate.get("source_records", []) or []:
        if isinstance(rec, dict):
            rec_title = clean_text(rec.get("title"))
            if rec_title and rec_title.lower() != name.lower():
                return rec_title
    return title or name


def trim_title_prefix(title: str, name: str) -> str:
    title = clean_text(title)
    name = clean_text(name)
    if not title:
        return ""
    if name and title.lower().startswith(name.lower() + ":"):
        return clean_text(title[len(name) + 1:])
    return title


def evidence_text(candidate: dict) -> str:
    parts = [
        candidate.get("name", ""),
        candidate.get("title", ""),
        candidate.get("scope", ""),
        candidate.get("category", ""),
        candidate.get("downstream_tasks", ""),
        candidate.get("input_modality", ""),
        candidate.get("architecture", ""),
    ]
    for ev in candidate.get("source_evidence", []) or []:
        if isinstance(ev, dict):
            parts.extend([ev.get("detected_name", ""), ev.get("detected_title", ""), ev.get("section", "")])
    for rec in candidate.get("source_records", []) or []:
        if isinstance(rec, dict):
            parts.extend([rec.get("name", ""), rec.get("title", ""), rec.get("section", ""), rec.get("raw_row", "")])
            cols = rec.get("raw_columns", {})
            if isinstance(cols, dict):
                parts.extend(cols.values())
    return " ".join(clean_text(p) for p in parts if p)


def infer_task_tags_from_text(text: str) -> list[str]:
    lower = clean_text(text).lower()
    tags = []
    for tag, needles in TASK_PATTERNS:
        if any(needle in lower for needle in needles) and tag not in tags:
            tags.append(tag)
    return tags


def task_text_from_columns(candidate: dict) -> str:
    values = []
    for rec in candidate.get("source_records", []) or []:
        if not isinstance(rec, dict):
            continue
        cols = rec.get("raw_columns", {})
        if not isinstance(cols, dict):
            continue
        for key, value in cols.items():
            key_l = str(key).lower()
            if any(w in key_l for w in ["task", "tasks", "attribute", "evaluation", "application"]):
                text = clean_text(value)
                if text and text not in values:
                    values.append(text)
    return "; ".join(values)


def derive_task_tags(candidate: dict) -> list[str]:
    existing = [clean_text(x) for x in candidate.get("task_tags", []) or [] if clean_text(x)]
    inferred = infer_task_tags_from_text(evidence_text(candidate))
    out = []
    for tag in existing + inferred:
        if tag and tag not in out:
            out.append(tag)
    return out


def derive_downstream_tasks(candidate: dict, entry_kind: str = "model") -> str:
    current = clean_text(candidate.get("downstream_tasks"))
    if current and not is_placeholder(current):
        return current

    column_text = task_text_from_columns(candidate)
    if column_text and not is_placeholder(column_text):
        return column_text

    tags = derive_task_tags(candidate)
    if tags:
        return "; ".join(tags)

    title = public_title(candidate)
    title_tags = infer_task_tags_from_text(title)
    if title_tags:
        return "; ".join(title_tags)

    if entry_kind == "benchmark":
        return "Benchmarking and evaluation for Earth observation models."
    return "General remote sensing representation learning and downstream adaptation."


def derive_scope(candidate: dict, entry_kind: str = "model") -> str:
    current = clean_text(candidate.get("scope"))
    if current and not is_placeholder(current):
        return current

    name = clean_text(candidate.get("name"))
    title = public_title(candidate)
    title_body = trim_title_prefix(title, name)
    if title_body:
        return title_body
    if title:
        return title

    tasks = derive_downstream_tasks(candidate, entry_kind)
    if entry_kind == "benchmark":
        return f"Benchmark or dataset resource for {tasks.lower()}"
    return f"Earth observation foundation model for {tasks.lower()}"


def derive_category(candidate: dict, entry_kind: str = "model") -> str:
    current = clean_text(candidate.get("category"))
    current_l = current.lower()
    if current and not any(word in current_l for word in ["candidate", "needs review"]):
        return current

    text = evidence_text(candidate).lower()
    if entry_kind == "benchmark":
        if "pre-training" in text or "pretraining" in text:
            return "Pre-training dataset"
        if "embedding" in text:
            return "Embedding dataset"
        if "benchmark" in text or "bench" in text:
            return "Benchmark"
        return "Dataset"

    if "vision-language" in text or "vision language" in text or "mllm" in text or "llm" in text:
        return "Vision-language EO foundation model"
    if "generative" in text or "diffusion" in text or "any-to-any" in text:
        return "Generative / multimodal EO foundation model"
    if "sar" in text or "radar" in text:
        return "SAR / radar EO foundation model"
    if "hyperspectral" in text:
        return "Hyperspectral EO foundation model"
    if "climate" in text or "weather" in text or "earth system" in text:
        return "Earth-system / climate foundation model"
    return "Earth observation foundation model"


def derive_modalities(candidate: dict) -> list[str]:
    tags = [clean_text(x) for x in candidate.get("modality_tags", []) or [] if clean_text(x)]
    inferred = infer_modality_tags(evidence_text(candidate))
    text = evidence_text(candidate).lower()
    extra = []
    modality_rules = [
        ("hyperspectral", ("hyperspectral", " hsi", "spectral-spatial")),
        ("multispectral", ("multispectral", "multi-spectral", "sentinel-2", "sentinel 2", "landsat", "surface reflectance", "spectral")),
        ("SAR", (" sar", "synthetic aperture radar", "sentinel-1", "sentinel 1", "radar")),
        ("LiDAR", ("lidar", "gedi", "icesat")),
        ("DEM", ("dem", "elevation", "topography")),
        ("temporal", ("temporal", "time-series", "time series", "spatio-temporal", "spatiotemporal")),
        ("text", ("vision-language", "vision language", "caption", "text", "vqa", "language-guided")),
        ("aerial / RGB imagery", ("aerial", "uav", "drone", "rgb", "high-resolution remote sensing image")),
        ("climate", ("climate", "weather", "meteorological", "era5")),
    ]
    for tag, needles in modality_rules:
        if any(needle in text for needle in needles):
            extra.append(tag)
    out = []
    for tag in tags + inferred + extra:
        if tag and tag not in out:
            out.append(tag)
    if "Contrastive / CLIP" in out and "Contrastive" in out:
        out.remove("Contrastive")
    return out


def derive_architectures(candidate: dict) -> list[str]:
    tags = [clean_text(x) for x in candidate.get("architecture_tags", []) or [] if clean_text(x)]
    inferred = infer_architecture_tags(evidence_text(candidate))
    text = evidence_text(candidate).lower()
    extra = []
    architecture_rules = [
        ("MAE / masked modeling", ("mae", "masked autoencoder", "masked image modeling", "masked feature modeling", "masked modeling", "mim")),
        ("Transformer", ("transformer", "vision transformer", " vit", "swin")),
        ("Contrastive / CLIP", ("contrastive", "clip", "alignment")),
        ("Vision-language", ("vision-language", "vision language", "mllm", "llm", "llava", "vqa")),
        ("State-space", ("mamba", "state space", "state-space")),
        ("Generative", ("diffusion", "generative", "text-to-image", "text-driven", "latent image modeling")),
        ("Agent", ("agent", "tool-augmented")),
    ]
    for tag, needles in architecture_rules:
        if any(needle in text for needle in needles):
            extra.append(tag)
    out = []
    for tag in tags + inferred + extra:
        if tag and tag not in out:
            out.append(tag)
    return out


def derive_evaluation_count(candidate: dict) -> int | None:
    explicit = candidate.get("reported_downstream_task_count")
    try:
        number = int(explicit)
        if number > 0:
            return number
    except Exception:
        pass

    text = evidence_text(candidate)
    lower = text.lower()
    matches = re.findall(r"\b(\d{1,2})\s+(?:downstream\s+)?(?:tasks?|evaluations?|benchmarks?)\b", lower)
    numeric = [int(m) for m in matches if 0 < int(m) <= 50]
    if numeric:
        return max(numeric)

    task_count = len(derive_task_tags(candidate))
    if task_count:
        return task_count
    return None


def landscape_score(candidate: dict) -> float:
    """Broad, public-facing score for the landscape Y axis.

    This is not a leaderboard metric. It spreads entries by evidence breadth:
    task labels/evaluation count, modality breadth, architecture detail, and
    availability of primary source links.
    """
    task_count = derive_evaluation_count(candidate) or len(derive_task_tags(candidate)) or 1
    modalities = max(1, len(derive_modalities(candidate)))
    architectures = max(1, len(derive_architectures(candidate)))
    links = sum(bool(candidate.get(k)) for k in ["paper_url", "code_url", "weights_url", "project_url"])
    access = str(candidate.get("access") or candidate.get("openness") or "").lower()
    access_bonus = 1.0 if access == "open" else 0.6 if access == "partial" else 0.2 if access == "unknown" else 0.0
    source_count = len(candidate.get("source_evidence", []) or [])
    score = task_count * 0.9 + modalities * 0.8 + architectures * 0.5 + links * 0.7 + access_bonus + min(source_count, 3) * 0.25
    return round(max(score, 1.0), 2)
