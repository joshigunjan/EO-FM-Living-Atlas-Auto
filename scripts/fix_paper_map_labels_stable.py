#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER_MAP = ROOT / "data" / "paper-map.json"

STABLE_CLUSTER_LABELS = {
    0: "Self-Supervised EO Encoders",
    1: "Geospatial Reasoning and Agents",
    2: "Remote-Sensing Vision Tasks",
    3: "Representation Learning and Adaptation",
    4: "Benchmarks and Evaluation",
    5: "Vision-Language EO Models",
    6: "Generative Geospatial Models",
    7: "Scaling and Model Capacity",
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
