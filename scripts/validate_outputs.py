from __future__ import annotations

from collections import Counter

from jsonschema import Draft202012Validator

from lib_utils import DATA, dump_json, load_json

ROOT = DATA.parent
CATALOGUE_PATH = DATA / "catalogue.json"
BENCHMARKS_PATH = DATA / "benchmarks.json"
METADATA_PATH = DATA / "metadata.json"
SEED_PATH = DATA / "manual_seed_catalogue.json"
SUPPLEMENT_PATH = DATA / "supplemental_catalogue.json"
CATALOGUE_SCHEMA_PATH = ROOT / "schema" / "catalogue.schema.json"
REPORT_PATH = DATA / "validation-summary.json"

SURVEY_TERMS = ("survey", "review", "commentary", "taxonomy", "genealogy", "open problems")
PLACEHOLDER_TERMS = ("candidate benchmark", "candidate earth observation", "needs curator review", "to be verified", "needs review")
BAD_PUBLIC_NAMES = ("unnamed candidate", "unnamed entry")
BAD_MODALITY_LABELS = ("remote sensing imagery",)


def duplicate_ids(entries: list[dict]) -> list[str]:
    ids = [entry.get("id") for entry in entries if entry.get("id")]
    return sorted([id_ for id_, count in Counter(ids).items() if count > 1])



def catalogue_by_id(entries: list[dict]) -> dict[str, dict]:
    return {str(entry.get("id")): entry for entry in entries if entry.get("id")}


def add_regression_error(errors: list[dict], condition: bool, path: list, message: str) -> None:
    if not condition:
        errors.append({"file": str(CATALOGUE_PATH), "path": path, "message": message})


def main() -> int:
    catalogue = load_json(CATALOGUE_PATH, [])
    benchmarks = load_json(BENCHMARKS_PATH, [])
    metadata = load_json(METADATA_PATH, {}) or {}
    schema = load_json(CATALOGUE_SCHEMA_PATH, {})
    errors = []
    warnings = []

    validator = Draft202012Validator(schema)
    for err in sorted(validator.iter_errors(catalogue), key=lambda e: list(e.path)):
        errors.append({"file": str(CATALOGUE_PATH), "path": list(err.path), "message": err.message})

    catalogue_dupes = duplicate_ids(catalogue)
    if catalogue_dupes:
        errors.append({"file": str(CATALOGUE_PATH), "path": ["id"], "message": f"Duplicate catalogue ids: {catalogue_dupes}"})

    benchmark_dupes = duplicate_ids(benchmarks)
    if benchmark_dupes:
        errors.append({"file": str(BENCHMARKS_PATH), "path": ["id"], "message": f"Duplicate benchmark ids: {benchmark_dupes}"})

    for index, entry in enumerate(catalogue):
        entry_type = entry.get("entry_type", "model")
        if entry_type != "model":
            errors.append({"file": str(CATALOGUE_PATH), "path": [index, "entry_type"], "message": f"Non-model entry in model catalogue: {entry_type}"})
        if str(entry.get("name", "")).strip().lower() in BAD_PUBLIC_NAMES:
            errors.append({"file": str(CATALOGUE_PATH), "path": [index, "name"], "message": "Public catalogue row has no usable model name.", "name": entry.get("name")})
        text = " ".join(str(entry.get(k, "")) for k in ["name", "title", "category"]).lower()
        if any(term in text for term in SURVEY_TERMS):
            warnings.append({"file": str(CATALOGUE_PATH), "path": [index], "message": "Catalogue row contains survey/review wording; verify classification.", "name": entry.get("name")})
        public_text = " ".join(str(entry.get(k, "")) for k in ["scope", "downstream_tasks"]).lower()
        if any(term in public_text for term in PLACEHOLDER_TERMS):
            errors.append({"file": str(CATALOGUE_PATH), "path": [index], "message": "Public catalogue row contains placeholder review wording.", "name": entry.get("name")})
        modality_text = str(entry.get("input_modality", "")).strip().lower()
        if modality_text in BAD_MODALITY_LABELS:
            errors.append({"file": str(CATALOGUE_PATH), "path": [index, "input_modality"], "message": "Public catalogue row uses a vague modality label.", "name": entry.get("name")})

    for index, entry in enumerate(benchmarks):
        public_text = " ".join(str(entry.get(k, "")) for k in ["scope", "tasks"]).lower()
        if any(term in public_text for term in PLACEHOLDER_TERMS):
            errors.append({"file": str(BENCHMARKS_PATH), "path": [index], "message": "Public benchmark row contains placeholder review wording.", "name": entry.get("name")})

    if metadata.get("entry_count") not in {None, len(catalogue)}:
        errors.append({"file": str(METADATA_PATH), "path": ["entry_count"], "message": f"metadata entry_count={metadata.get('entry_count')} but catalogue has {len(catalogue)} rows"})
    if metadata.get("benchmark_dataset_count") not in {None, len(benchmarks)}:
        errors.append({"file": str(METADATA_PATH), "path": ["benchmark_dataset_count"], "message": f"metadata benchmark_dataset_count={metadata.get('benchmark_dataset_count')} but benchmarks has {len(benchmarks)} rows"})

    # High-value regression checks for reviewed entries and version names.
    by_id = catalogue_by_id(catalogue)
    add_regression_error(errors, "olmoearth-v1-1" not in by_id, ["olmoearth-v1-1"], "Obsolete OlmoEarth v1.1 row should not be published after v1.2 release.")
    add_regression_error(errors, "olmoearth-v1-2" in by_id, ["olmoearth-v1-2"], "Latest OlmoEarth v1.2 row is missing.")

    terramind = by_id.get("terramind", {})
    add_regression_error(errors, terramind.get("modality_complexity_tier_key") == "generalist", ["terramind", "modality_complexity_tier_key"], "TerraMind must remain classified as an any-to-any generalist model.")
    add_regression_error(errors, int(terramind.get("reported_downstream_task_count") or 0) >= 9, ["terramind", "reported_downstream_task_count"], "TerraMind downstream evidence collapsed below the reviewed benchmark count.")

    for model_id in ["prithvi-eo-1-0", "prithvi-eo-2-0", "earthpt"]:
        entry = by_id.get(model_id, {})
        add_regression_error(errors, entry.get("modality_complexity_tier_key") == "single_modality", [model_id, "modality_complexity_tier_key"], f"{model_id} should be a single-modality encoder/time-series model, not generalist.")

    for model_id in ["olmoearth", "olmoearth-v1-2"]:
        entry = by_id.get(model_id, {})
        add_regression_error(errors, entry.get("modality_complexity_tier_key") == "multi_modality", [model_id, "modality_complexity_tier_key"], f"{model_id} should be a multi-modality encoder, not an any-to-any generalist model.")


    for required_id in ["dofa-plus", "satmae-plus-plus", "skysense-plus-plus"]:
        add_regression_error(errors, required_id in by_id, [required_id], f"Reviewed versioned release {required_id} is missing.")

    for forbidden_id in ["geo3dvqa", "geollm-qa", "univearth", "satlas", "choice"]:
        add_regression_error(errors, forbidden_id not in by_id, [forbidden_id], f"Benchmark/dataset resource {forbidden_id} must not appear in the model catalogue.")

    benchmark_urls = Counter(str(entry.get("dataset_url") or entry.get("project_url") or "").strip().lower().rstrip("/") for entry in benchmarks if entry.get("dataset_url") or entry.get("project_url"))
    repeated_urls = sorted(url for url, count in benchmark_urls.items() if url and count > 1)
    if repeated_urls:
        errors.append({"file": str(BENCHMARKS_PATH), "path": ["dataset_url"], "message": f"Duplicate benchmark/dataset URLs: {repeated_urls}"})

    if metadata.get("catalogue_entries") is not None:
        errors.append({"file": str(METADATA_PATH), "path": ["catalogue_entries"], "message": "Stale catalogue_entries field should be removed; use entry_count."})

    # Reviewed seed/supplement rows must win over weak automatic duplicates.
    curated = (load_json(SUPPLEMENT_PATH, []) or []) + (load_json(SEED_PATH, []) or [])
    for curated_entry in curated:
        if not isinstance(curated_entry, dict):
            continue
        paper_url = str(curated_entry.get("paper_url") or curated_entry.get("primary_source_url") or "").strip().lower()
        if not paper_url:
            continue
        matches = [entry for entry in catalogue if str(entry.get("paper_url") or "").strip().lower() == paper_url]
        if matches and all(str(entry.get("review_status") or "").startswith("upstream") for entry in matches):
            errors.append({"file": str(CATALOGUE_PATH), "path": ["paper_url", paper_url], "message": "An automatic row overrode an available reviewed curated entry."})

    report = {
        "catalogue_count": len(catalogue),
        "benchmark_count": len(benchmarks),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }
    dump_json(REPORT_PATH, report)

    if errors:
        print(f"Output validation failed with {len(errors)} error(s). See {REPORT_PATH}.")
        return 1
    print(f"Output validation passed for {len(catalogue)} catalogue entries and {len(benchmarks)} benchmark entries.")
    if warnings:
        print(f"Output validation produced {len(warnings)} warning(s). See {REPORT_PATH}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
