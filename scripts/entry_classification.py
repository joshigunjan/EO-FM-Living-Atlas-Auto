from __future__ import annotations

import re

from lib_utils import normalize_name, slugify, strip_md

ENTRY_TYPES = {
    "model": "Reusable Earth observation foundation model or framework",
    "benchmark_dataset": "Benchmark, evaluation dataset, pre-training dataset, or embedding dataset",
    "survey_review": "Survey, review, commentary, taxonomy, or position paper",
    "paper_method": "Downstream task method or application paper, not a new foundation model",
    "unknown": "Insufficient evidence for a stable catalogue type",
}

MODEL_ENTRY_TYPES = {"model"}
NON_MODEL_ENTRY_TYPES = {"benchmark_dataset", "survey_review", "paper_method", "unknown"}

SURVEY_TERMS = (
    "survey",
    "review",
    "commentary",
    "taxonomy",
    "genealogy",
    "open problems",
    "challenges and applications",
    "charting new territories",
    "position paper",
    "meta-analysis",
    "foundations taxonomy",
)

BENCHMARK_SECTION_TERMS = (
    "benchmark",
    "dataset",
    "pre-training data",
    "pretraining data",
    "embedding data",
    "embeddings data",
    "evaluation",
)

BENCHMARK_TEXT_TERMS = (
    "benchmark",
    "benchmarking",
    "-bench",
    " bench",
    "dataset",
    "evaluation suite",
    "pre-training dataset",
    "pretraining dataset",
)

MODEL_SECTION_TERMS = (
    "vision foundation model",
    "generative foundation model",
    "language foundation model",
    "vision-language foundation model",
    "vision-location foundation model",
    "vision-audio foundation model",
    "remote sensing vision",
    "remote sensing generative",
    "foundation models",
)

PAPER_METHOD_TERMS = (
    "using foundation model",
    "using foundation models",
    "with foundation model",
    "with foundation models",
    "based on foundation model",
    "based on foundation models",
    "built on foundation model",
    "fine-tuning foundation",
    "fine tuning foundation",
)

KNOWN_BENCHMARK_RESOURCE_NAMES = {
    "geo3dvqa", "geollmqa", "geollm qa", "univearth", "satlas", "choice",
    "rs5m", "fitrs", "fit-rs",
}

BAD_PUBLIC_NAMES = {
    "",
    "-",
    "--",
    "n/a",
    "na",
    "none",
    "unknown",
    "entry",
    "unnamed entry",
    "unnamed candidate",
}


def _clean(value: object) -> str:
    return strip_md(str(value or "")).strip()


def _norm_text(value: object) -> str:
    return _clean(value).lower().replace("_", " ")


def source_evidence(candidate: dict) -> list[dict]:
    return [ev for ev in candidate.get("source_evidence", []) or [] if isinstance(ev, dict)]


def source_records(candidate: dict) -> list[dict]:
    return [rec for rec in candidate.get("source_records", []) or [] if isinstance(rec, dict)]


def source_sections(candidate: dict) -> list[str]:
    sections = []
    for ev in source_evidence(candidate):
        section = _norm_text(ev.get("section"))
        if section:
            sections.append(section)
    for rec in source_records(candidate):
        section = _norm_text(rec.get("section"))
        if section and section not in sections:
            sections.append(section)
    return sections


def resource_types(candidate: dict) -> set[str]:
    out = set()
    if candidate.get("resource_type"):
        out.add(str(candidate["resource_type"]).strip())
    for ev in source_evidence(candidate):
        if ev.get("resource_type"):
            out.add(str(ev["resource_type"]).strip())
    for rec in source_records(candidate):
        if rec.get("resource_type"):
            out.add(str(rec["resource_type"]).strip())
    return {x for x in out if x}


def entry_text(candidate: dict) -> str:
    parts = [
        candidate.get("name", ""),
        candidate.get("title", ""),
        candidate.get("category", ""),
        candidate.get("scope", ""),
        candidate.get("input_modality", ""),
        candidate.get("architecture", ""),
        candidate.get("downstream_tasks", ""),
    ]
    for ev in source_evidence(candidate):
        parts.extend([
            ev.get("detected_name", ""),
            ev.get("detected_title", ""),
            ev.get("section", ""),
        ])
    for rec in source_records(candidate):
        parts.extend([
            rec.get("name", ""),
            rec.get("title", ""),
            rec.get("section", ""),
            rec.get("raw_row", ""),
        ])
    return " ".join(_clean(p) for p in parts if p)


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        if " " in term or "-" in term:
            if term in text:
                return True
            continue
        if re.search(rf"\b{re.escape(term)}s?\b", text):
            return True
    return False


def survey_evidence_text(candidate: dict) -> str:
    parts = [candidate.get("name", ""), candidate.get("title", "")]
    for ev in source_evidence(candidate):
        parts.extend([ev.get("detected_name", ""), ev.get("detected_title", ""), ev.get("section", "")])
    for rec in source_records(candidate):
        parts.extend([rec.get("name", ""), rec.get("title", ""), rec.get("section", ""), rec.get("raw_row", "")])
    text = _norm_text(" ".join(_clean(p) for p in parts if p))
    # Generated placeholder text frequently says "needs review"; that is not
    # evidence that the upstream resource is a review article.
    for placeholder in ("needs review", "curator review", "review manually", "reviewer"):
        text = text.replace(placeholder, "")
    return text


def has_survey_evidence(candidate: dict) -> bool:
    text = survey_evidence_text(candidate)
    sections = " ".join(source_sections(candidate))
    rtypes = resource_types(candidate)
    return "survey_review" in rtypes or _has_any(sections, SURVEY_TERMS) or _has_any(text, SURVEY_TERMS)


def has_benchmark_evidence(candidate: dict) -> bool:
    if has_strong_benchmark_evidence(candidate):
        return True
    text = _norm_text(" ".join([
        candidate.get("name", ""),
        candidate.get("title", ""),
        candidate.get("category", ""),
        candidate.get("scope", ""),
    ]))
    return _has_any(text, BENCHMARK_TEXT_TERMS)


def has_strong_benchmark_evidence(candidate: dict) -> bool:
    rtypes = resource_types(candidate)
    if rtypes & {"benchmark", "dataset", "benchmark_dataset"}:
        return True
    sections = " ".join(source_sections(candidate))
    return _has_any(sections, BENCHMARK_SECTION_TERMS)


def has_benchmark_identity(candidate: dict) -> bool:
    parts = [candidate.get("name", ""), candidate.get("title", "")]
    for ev in source_evidence(candidate):
        parts.extend([ev.get("detected_name", ""), ev.get("detected_title", "")])
    text = _norm_text(" ".join(_clean(p) for p in parts if p))
    if re.search(r"\bbenchmark(s|ing)?\b", text):
        return True
    if re.search(r"(^|[\s_-])bench($|[\s_-])", text):
        return True
    for name in candidate_model_names(candidate):
        low = name.lower()
        if low.endswith("bench") or "-bench" in low or "_bench" in low:
            return True
    return False


def has_model_section_evidence(candidate: dict) -> bool:
    sections = " ".join(source_sections(candidate))
    return _has_any(sections, MODEL_SECTION_TERMS)


def _url_tail(url: object) -> str:
    value = str(url or "").split("?")[0].rstrip("/")
    if not value:
        return ""
    parts = [p for p in value.split("/") if p]
    lower = value.lower()
    if ("github.com" in lower or "huggingface.co" in lower) and len(parts) >= 2:
        return _clean(parts[-1])
    return ""


def is_dataset_url(url: object) -> bool:
    lower = str(url or "").lower()
    return "huggingface.co/datasets/" in lower or "/datasets/" in lower


def has_model_artifact(candidate: dict) -> bool:
    weights = candidate.get("weights_url") or ""
    if weights and not is_dataset_url(weights):
        return True
    code = str(candidate.get("code_url") or "")
    if code and not re.search(r"(?i)(-bench|benchmark|dataset)", code):
        return True
    project = str(candidate.get("project_url") or "")
    if project and not is_dataset_url(project):
        return True
    return False


def looks_like_paper_title(name: object) -> bool:
    value = _clean(name)
    if not value:
        return False
    low = value.lower()
    normalized = low.replace("-", " ").replace("_", " ")
    words = normalized.split()
    if _has_any(normalized, SURVEY_TERMS):
        return True
    if low.startswith(("a ", "an ", "the ", "towards ", "toward ", "review ", "survey ")):
        return True
    if low.startswith(("awesome-", "awesome_", "awesome ")):
        return True
    return len(words) >= 6


def is_compact_model_name(name: object) -> bool:
    value = _clean(name)
    if value.lower() in BAD_PUBLIC_NAMES:
        return False
    if looks_like_paper_title(value):
        return False
    words = value.replace("-", " ").replace("_", " ").split()
    if ("-" in value or "_" in value) and len(words) > 3:
        return False
    if " " not in value and 2 <= len(value) <= 60:
        return True
    return 1 <= len(words) <= 3 and len(value) <= 60


def title_prefix_name(title: object) -> str:
    value = _clean(title)
    if ":" not in value:
        return ""
    prefix = _clean(value.split(":", 1)[0])
    if is_compact_model_name(prefix):
        return prefix
    return ""


def candidate_model_names(candidate: dict) -> list[str]:
    names = [
        candidate.get("name", ""),
        title_prefix_name(candidate.get("title", "")),
        _url_tail(candidate.get("code_url", "")),
        _url_tail(candidate.get("weights_url", "")),
        _url_tail(candidate.get("project_url", "")),
    ]
    names.extend(candidate.get("aliases", []) or [])
    for ev in source_evidence(candidate):
        names.append(ev.get("detected_name", ""))
        names.append(title_prefix_name(ev.get("detected_title", "")))

    out = []
    seen = set()
    for name in names:
        clean = _clean(name)
        key = normalize_name(clean)
        if clean and key not in seen:
            out.append(clean)
            seen.add(key)
    return out


def best_model_name(candidate: dict) -> str:
    for name in candidate_model_names(candidate):
        if is_compact_model_name(name):
            return name
    return ""


def has_model_identity(candidate: dict) -> bool:
    return bool(best_model_name(candidate) or has_model_artifact(candidate))


def looks_like_paper_method(candidate: dict) -> bool:
    text = _norm_text(entry_text(candidate))
    if _has_any(text, PAPER_METHOD_TERMS) and not has_model_identity(candidate):
        return True
    title = _norm_text(candidate.get("title", ""))
    name = _norm_text(candidate.get("name", ""))
    if not has_model_identity(candidate) and looks_like_paper_title(name or title):
        return True
    return False


def classify_entry(candidate: dict) -> tuple[str, str]:
    """Classify a candidate into the public atlas entry taxonomy.

    LLM-provided entry_type is trusted only for OpenAI-enriched candidates. For
    heuristic candidates, this function re-evaluates the evidence so old or
    stale generated files do not leak surveys into the model catalogue.
    """
    existing = str(candidate.get("entry_type") or "").strip()
    method = str(candidate.get("extraction_method") or "").lower()
    known_name = normalize_name(_clean(candidate.get("name") or candidate.get("title")))
    if known_name in KNOWN_BENCHMARK_RESOURCE_NAMES:
        return "benchmark_dataset", "Known benchmark, evaluation resource, or dataset."
    if existing in ENTRY_TYPES and method.startswith("openai:"):
        return existing, candidate.get("entry_type_reason") or "Classified by LLM extraction."

    benchmark = has_benchmark_evidence(candidate)
    strong_benchmark = has_strong_benchmark_evidence(candidate)
    benchmark_identity = has_benchmark_identity(candidate)
    survey = has_survey_evidence(candidate)
    model_section = has_model_section_evidence(candidate)
    model_identity = has_model_identity(candidate)
    pre = str(candidate.get("pre_classified_type") or "").strip()
    rtypes = resource_types(candidate)

    if survey and not strong_benchmark:
        return "survey_review", "Survey/review/commentary wording or section evidence was detected."

    if benchmark_identity and not (model_identity and not strong_benchmark):
        return "benchmark_dataset", "Benchmark/dataset naming or title evidence was detected."

    if strong_benchmark and not (model_section or model_identity or "model" in rtypes):
        return "benchmark_dataset", "Benchmark, dataset, pre-training-data, or evaluation evidence was detected."

    if looks_like_paper_method(candidate):
        return "paper_method", "The evidence looks like a downstream method or paper-only resource, not a reusable model."

    if benchmark and not model_identity and not strong_benchmark:
        return "paper_method", "Benchmark-related paper wording was detected, but no reusable benchmark/dataset artifact or model identity was found."

    if model_identity and not (benchmark and not model_section):
        return "model", "A compact model identity, model artifact, or model-section source evidence was detected."

    if pre == "model" or model_section or "model" in rtypes:
        if not looks_like_paper_title(candidate.get("name", "")):
            return "model", "Upstream section/resource evidence identifies this as a model candidate."

    if benchmark:
        return "benchmark_dataset", "Benchmark or dataset evidence was detected after model checks."

    return "unknown", "The available evidence is insufficient for automatic publication."


def public_model_id(candidate: dict) -> str:
    name = best_model_name(candidate) or candidate.get("name") or candidate.get("title") or "entry"
    return slugify(str(name), fallback="entry")
