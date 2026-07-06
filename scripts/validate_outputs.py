from __future__ import annotations

from collections import Counter

from jsonschema import Draft202012Validator

from lib_utils import DATA, dump_json, load_json

ROOT = DATA.parent
CATALOGUE_PATH = DATA / "catalogue.json"
BENCHMARKS_PATH = DATA / "benchmarks.json"
METADATA_PATH = DATA / "metadata.json"
CATALOGUE_SCHEMA_PATH = ROOT / "schema" / "catalogue.schema.json"
REPORT_PATH = DATA / "validation-summary.json"

SURVEY_TERMS = ("survey", "review", "commentary", "taxonomy", "genealogy", "open problems")
PLACEHOLDER_TERMS = ("candidate benchmark", "candidate earth observation", "needs curator review", "to be verified", "needs review")
BAD_PUBLIC_NAMES = ("unnamed candidate", "unnamed entry")
BAD_MODALITY_LABELS = ("remote sensing imagery",)


def duplicate_ids(entries: list[dict]) -> list[str]:
    ids = [entry.get("id") for entry in entries if entry.get("id")]
    return sorted([id_ for id_, count in Counter(ids).items() if count > 1])


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
