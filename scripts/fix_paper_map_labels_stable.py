#!/usr/bin/env python3
"""Fix public semantic-cluster labels in data/paper-map.json.

Run from the repository root:
    python scripts/fix_paper_map_labels_stable.py

This does not recompute embeddings, UMAP, or KMeans. It only applies stable
public labels by cluster id and synchronizes each point's cluster_label field.
"""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("data/paper-map.json")

STABLE_LABELS_BY_CLUSTER_ID = {
    0: "Self-Supervised EO Encoders",
    1: "Geospatial Reasoning and Agents",
    2: "Remote-Sensing Vision Tasks",
    3: "Representation Learning and Adaptation",
    4: "Benchmarks and Evaluation",
    5: "Vision-Language EO Models",
    6: "Generative Geospatial Models",
    7: "Scaling and Model Capacity",
}

payload = json.loads(PATH.read_text(encoding="utf-8"))

labels_seen = set()
for cluster in payload.get("clusters", []):
    cluster_id = int(cluster["id"])
    label = STABLE_LABELS_BY_CLUSTER_ID.get(cluster_id, f"Semantic Theme {cluster_id + 1}")
    cluster["label"] = label
    labels_seen.add(cluster_id)

for point in payload.get("points", []):
    cluster_id = int(point["cluster_id"])
    point["cluster_label"] = STABLE_LABELS_BY_CLUSTER_ID.get(
        cluster_id,
        f"Semantic Theme {cluster_id + 1}",
    )

payload.setdefault("clustering", {})["label_method"] = "curated-stable-labels"
PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

print(f"Updated {PATH} with stable labels for {len(labels_seen)} clusters.")
