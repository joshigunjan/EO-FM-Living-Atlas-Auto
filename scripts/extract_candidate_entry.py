from __future__ import annotations

import json
import os
from pathlib import Path

from lib_utils import DATA, dump_json, infer_access, load_json

IN_PATH = DATA / "candidates" / "latest-candidates.with-metadata.json"
if not IN_PATH.exists():
    IN_PATH = DATA / "candidates" / "latest-candidates.json"
OUT_PATH = DATA / "candidates" / "latest-candidates.extracted.json"

PARADIGMS = {
    "transformer_masked": "Transformer / masked-reconstruction encoder",
    "joint_embedding": "Joint-embedding / contrastive-predictive encoder",
    "vision_language": "Vision-language / EO MLLM",
    "state_space": "State-space / sequence model",
    "embedding_product": "Embedding product / representation field",
    "generative_hybrid": "Any-to-any generative / hybrid multimodal system",
    "needs_review": "Needs review",
}

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "name", "title", "scope", "category", "input_modality", "modality_tags",
        "architecture", "architecture_tags", "modelling_paradigm_key", "modelling_paradigm",
        "downstream_tasks", "task_tags", "training_scale", "access", "access_label",
        "modality_complexity_tier_key", "modality_complexity_tier", "modality_complexity_score",
        "reported_downstream_task_count", "reported_downstream_task_count_basis",
        "extraction_confidence", "needs_review", "notes_for_reviewer"
    ],
    "properties": {
        "name": {"type": "string"},
        "title": {"type": "string"},
        "scope": {"type": "string"},
        "category": {"type": "string"},
        "input_modality": {"type": "string"},
        "modality_tags": {"type": "array", "items": {"type": "string"}},
        "architecture": {"type": "string"},
        "architecture_tags": {"type": "array", "items": {"type": "string"}},
        "modelling_paradigm_key": {"enum": list(PARADIGMS.keys())},
        "modelling_paradigm": {"type": "string"},
        "downstream_tasks": {"type": "string"},
        "task_tags": {"type": "array", "items": {"type": "string"}},
        "training_scale": {"type": "string"},
        "access": {"enum": ["open", "partial", "closed", "unknown"]},
        "access_label": {"enum": ["Open source", "Partial access", "Closed source", "Unknown"]},
        "modality_complexity_tier_key": {"enum": ["single_modality", "multi_modality", "vision_language", "generalist", "needs_review"]},
        "modality_complexity_tier": {"type": "string"},
        "modality_complexity_score": {"type": ["number", "null"]},
        "reported_downstream_task_count": {"type": ["number", "null"]},
        "reported_downstream_task_count_basis": {"type": "string"},
        "extraction_confidence": {"enum": ["high", "medium", "low"]},
        "needs_review": {"type": "boolean"},
        "notes_for_reviewer": {"type": "string"},
    },
}

SYSTEM_PROMPT = """You curate a structured catalogue of Earth observation foundation models.
Extract only information supported by the provided upstream row, paper metadata, abstract, README excerpt, and links.
Do not invent exact downstream task counts or access status. Use null and needs_review when uncertain.
Access labels mean: Open source = paper plus usable code and/or weights are available; Partial access = some links exist but not full code/weights; Closed source = explicitly unavailable; Unknown = not enough evidence.
Keep wording compact and scientific.
"""


def call_openai(candidate: dict) -> dict | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except Exception:
        return None
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)
    user_payload = {
        "candidate": {k: candidate.get(k) for k in ["name", "title", "paper_url", "code_url", "weights_url", "project_url", "source_evidence", "conflicts"]},
        "metadata": candidate.get("metadata", {}),
        "allowed_modelling_paradigms": PARADIGMS,
    }
    try:
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "eo_fm_candidate_entry",
                    "strict": True,
                    "schema": SCHEMA,
                }
            },
        )
    except Exception as exc:
        print(f"LLM extraction skipped for {candidate.get('name', candidate.get('id'))}: {exc}")
        return None
    text = getattr(response, "output_text", None)
    if not text:
        # Compatibility fallback for SDK variants.
        text = str(response)
    try:
        return json.loads(text)
    except Exception:
        # Try to recover the first JSON object if the SDK stringified extra metadata.
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end+1])
    return None


def heuristic_enrichment(candidate: dict) -> dict:
    urls = []
    for field in ["paper_url", "code_url", "weights_url", "project_url"]:
        if candidate.get(field):
            urls.append(candidate[field])
    access, access_label = infer_access(urls)
    candidate["access"] = candidate.get("access") or access
    candidate["access_label"] = candidate.get("access_label") or access_label
    candidate["extraction_confidence"] = candidate.get("extraction_confidence") or "low"
    candidate["needs_review"] = True
    candidate["review_status"] = "candidate"
    candidate.setdefault("notes_for_reviewer", "Heuristic candidate. Run LLM extraction or review manually before verification.")
    candidate["extraction_method"] = "heuristic"
    return candidate


def main() -> int:
    candidates = load_json(IN_PATH, [])
    enriched = []
    for cand in candidates:
        llm = call_openai(cand)
        if llm:
            protected = {k: cand.get(k) for k in ["id", "paper_url", "code_url", "weights_url", "project_url", "source_records", "source_evidence", "deduplication_keys", "aliases", "conflicts", "metadata", "sync_detected_at"]}
            cand.update(llm)
            cand.update(protected)
            cand["review_status"] = "candidate"
            cand["needs_review"] = True
            cand["extraction_method"] = f"openai:{os.getenv('OPENAI_MODEL', 'gpt-5.5')}"
        else:
            cand = heuristic_enrichment(cand)
        enriched.append(cand)
    dump_json(OUT_PATH, enriched)
    print(f"Extracted/enriched {len(enriched)} candidates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
