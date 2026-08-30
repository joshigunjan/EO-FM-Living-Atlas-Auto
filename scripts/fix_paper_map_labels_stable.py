#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER_MAP = ROOT / "data" / "paper-map.json"

STABLE_CLUSTER_LABELS = {
    0: "Representation and Pretraining",
    1: "Vision-Language and Geospatial Reasoning",
    2: "Multimodal and Sensor Fusion",
    3: "Generative and Simulation Models",
    4: "Benchmarks, Datasets, and Evaluation",
    5: "Application and Task-Specific EO Models",
}

data = json.loads(PAPER_MAP.read_text(encoding="utf-8"))

for cluster in data.get("clusters", []):
    cluster_id = int(cluster["id"])
    cluster["label"] = STABLE_CLUSTER_LABELS.get(
        cluster_id,
        f"Semantic Cluster {cluster_id + 1}",
    )

label_by_id = {
    int(cluster["id"]): cluster["label"]
    for cluster in data.get("clusters", [])
}

for point in data.get("points", []):
    cluster_id = int(point["cluster_id"])
    point["cluster_label"] = label_by_id.get(
        cluster_id,
        f"Semantic Cluster {cluster_id + 1}",
    )

data.setdefault("clustering", {})["label_method"] = "curated-stable"

PAPER_MAP.write_text(
    json.dumps(data, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("Updated stable paper-map labels:")
for cluster in data.get("clusters", []):
    print(f'{cluster["id"]}: {cluster["label"]} ({cluster["size"]} papers)')
