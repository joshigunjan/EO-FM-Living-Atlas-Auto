from __future__ import annotations

from collections import Counter

from jsonschema import Draft202012Validator

from lib_utils import DATA, dump_json, load_json

IN_PATH = DATA / "candidates" / "latest-candidates.extracted.json"
if not IN_PATH.exists():
    IN_PATH = DATA / "candidates" / "latest-candidates.json"
SCHEMA_PATH = DATA.parent / "schema" / "candidate.schema.json"
REPORT_PATH = DATA / "candidates" / "validation-report.json"


def main() -> int:
    candidates = load_json(IN_PATH, [])
    schema = load_json(SCHEMA_PATH, {})
    validator = Draft202012Validator(schema)
    errors = []
    for err in sorted(validator.iter_errors(candidates), key=lambda e: e.path):
        errors.append({"path": list(err.path), "message": err.message})

    ids = [c.get("id") for c in candidates if c.get("id")]
    duplicate_ids = [id_ for id_, count in Counter(ids).items() if count > 1]
    if duplicate_ids:
        errors.append({"path": ["id"], "message": f"Duplicate candidate ids: {duplicate_ids}"})

    report = {
        "candidate_count": len(candidates),
        "duplicate_ids": duplicate_ids,
        "error_count": len(errors),
        "errors": errors,
        "note": "Candidate entries may still need scientific review even when schema validation passes.",
    }
    dump_json(REPORT_PATH, report)
    if errors:
        print(f"Validation completed with {len(errors)} warning/error(s). See {REPORT_PATH}.")
        # Do not fail the scheduled run: the PR should show the validation report for review.
        return 0
    print(f"Validated {len(candidates)} candidate entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
