#!/usr/bin/env python3
"""
Build a static semantic map of EO foundation-model and benchmark papers.

The script:
1. Reads data/catalogue.json and data/benchmarks.json.
2. Collects one record per unique paper.
3. Retrieves abstracts from arXiv, Crossref, OpenAlex, and optionally
   Semantic Scholar.
4. Creates OpenAI-compatible text embeddings.
5. Reduces them to two dimensions with UMAP (PCA fallback).
6. Clusters the original embeddings with K-Means.
7. Generates concise TF-IDF cluster labels.
8. Writes data/paper-map.json for a static GitHub Pages frontend.

The embedding endpoint is provider-independent. It can point to OpenAI,
Blablador, LM Studio, or another OpenAI-compatible endpoint.

Environment variables
---------------------
EMBEDDING_MODEL
    Required unless --allow-tfidf-fallback is used.
EMBEDDING_API_KEY
    Preferred API-key variable. Falls back to OPENAI_API_KEY and
    LLM_BACKEND_AUTH_TOKEN.
EMBEDDING_BASE_URL
    Optional OpenAI-compatible base URL. Leave unset for the default
    OpenAI endpoint.
SEMANTIC_SCHOLAR_API_KEY
    Optional. Used only as a final abstract-retrieval fallback.
OPENALEX_MAILTO
    Optional contact email sent to OpenAlex.
CROSSREF_MAILTO
    Optional contact email sent to Crossref.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import requests
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.preprocessing import normalize


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CATALOGUE_PATH = DATA / "catalogue.json"
BENCHMARKS_PATH = DATA / "benchmarks.json"
OUTPUT_PATH = DATA / "paper-map.json"
CACHE_DIR = DATA / "paper-map-cache"
ABSTRACT_CACHE_PATH = CACHE_DIR / "abstracts.json"
EMBEDDING_CACHE_PATH = CACHE_DIR / "embeddings.json"

GENERIC_CLUSTER_TERMS = {
    "remote",
    "sensing",
    "earth",
    "observation",
    "model",
    "models",
    "foundation",
    "image",
    "images",
    "data",
    "dataset",
    "datasets",
    "task",
    "tasks",
    "paper",
    "papers",
    "approach",
    "approaches",
    "method",
    "methods",
}

USER_AGENT = (
    "EO-FM-Living-Atlas/1.0 "
    "(semantic paper map; contact: "
    + (os.getenv("CROSSREF_MAILTO") or os.getenv("OPENALEX_MAILTO") or "not-provided")
    + ")"
)

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False),
        encoding="utf-8",
    )


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_url(url: str) -> str:
    value = str(url or "").strip()
    if not value:
        return ""
    value = value.replace("http://", "https://")
    value = value.split("#", 1)[0]
    if "arxiv.org/pdf/" in value:
        value = value.replace("arxiv.org/pdf/", "arxiv.org/abs/")
        value = re.sub(r"\.pdf$", "", value)
    return value.rstrip("/")


def extract_arxiv_id(url: str) -> str:
    match = re.search(
        r"arxiv\.org/(?:abs|pdf)/([a-z\-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?",
        str(url or ""),
        flags=re.I,
    )
    return match.group(1) if match else ""


def extract_doi(url: str) -> str:
    text = urllib.parse.unquote(str(url or ""))
    match = re.search(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", text, flags=re.I)
    if not match:
        return ""
    return match.group(1).rstrip(".,;)")


def paper_key(url: str, title: str) -> str:
    arxiv_id = extract_arxiv_id(url)
    if arxiv_id:
        return f"arxiv:{arxiv_id.lower()}"
    doi = extract_doi(url)
    if doi:
        return f"doi:{doi.lower()}"
    normalized = normalize_url(url)
    if normalized:
        return f"url:{normalized.lower()}"
    normalized_title = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"title:{normalized_title}"


def year_value(value: Any) -> int | None:
    try:
        year = int(value)
        if 1900 <= year <= 2100:
            return year
    except (TypeError, ValueError):
        pass
    return None


def collect_papers() -> list[dict[str, Any]]:
    catalogue = load_json(CATALOGUE_PATH, [])
    benchmarks = load_json(BENCHMARKS_PATH, [])
    grouped: dict[str, dict[str, Any]] = {}

    def add_record(
        *,
        entry: dict[str, Any],
        resource_type: str,
        title: str,
        summary: str,
        tasks: str,
        modalities: str,
        paper_url: str,
    ) -> None:
        title = clean_text(title or entry.get("name"))
        paper_url = normalize_url(paper_url)
        if not title or not paper_url:
            return

        key = paper_key(paper_url, title)
        record = grouped.get(key)

        associated = {
            "id": str(entry.get("id") or ""),
            "name": clean_text(entry.get("name")),
            "resource_type": resource_type,
            "year": year_value(entry.get("publication_year")),
        }

        if record is None:
            record = {
                "id": hashlib.sha1(key.encode("utf-8")).hexdigest()[:16],
                "paper_key": key,
                "title": title,
                "paper_url": paper_url,
                "year": year_value(entry.get("publication_year")),
                "resource_types": [],
                "associated_entries": [],
                "summary": clean_text(summary),
                "tasks": clean_text(tasks),
                "modalities": clean_text(modalities),
                "abstract": clean_text(entry.get("abstract")),
                "abstract_source": "catalogue" if entry.get("abstract") else "",
            }
            grouped[key] = record

        if resource_type not in record["resource_types"]:
            record["resource_types"].append(resource_type)

        if associated not in record["associated_entries"]:
            record["associated_entries"].append(associated)

        if not record.get("year"):
            record["year"] = associated["year"]
        if not record.get("summary"):
            record["summary"] = clean_text(summary)
        if not record.get("tasks"):
            record["tasks"] = clean_text(tasks)
        if not record.get("modalities"):
            record["modalities"] = clean_text(modalities)

    for entry in catalogue:
        add_record(
            entry=entry,
            resource_type="model",
            title=entry.get("title") or entry.get("name"),
            summary=entry.get("scope"),
            tasks=entry.get("downstream_tasks"),
            modalities=entry.get("input_modality"),
            paper_url=entry.get("paper_url"),
        )

    for entry in benchmarks:
        add_record(
            entry=entry,
            resource_type="benchmark",
            title=entry.get("title") or entry.get("name"),
            summary=entry.get("scope"),
            tasks=entry.get("tasks"),
            modalities=entry.get("modalities"),
            paper_url=entry.get("paper_url"),
        )

    return sorted(grouped.values(), key=lambda item: (item.get("year") or 9999, item["title"].lower()))


def fetch_arxiv_abstract(arxiv_id: str) -> tuple[str, int | None]:
    if not arxiv_id:
        return "", None

    response = session.get(
        "https://export.arxiv.org/api/query",
        params={"id_list": arxiv_id},
        timeout=30,
    )
    response.raise_for_status()

    root = ET.fromstring(response.text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", ns)
    if entry is None:
        return "", None

    summary = clean_text(entry.findtext("atom:summary", default="", namespaces=ns))
    published = entry.findtext("atom:published", default="", namespaces=ns)
    year = year_value(published[:4]) if published else None
    return summary, year


def reconstruct_openalex_abstract(inverted: dict[str, list[int]] | None) -> str:
    if not inverted:
        return ""
    positions: list[tuple[int, str]] = []
    for token, indexes in inverted.items():
        for index in indexes:
            positions.append((index, token))
    positions.sort()
    return clean_text(" ".join(token for _, token in positions))


def fetch_openalex_by_doi(doi: str) -> tuple[str, int | None]:
    if not doi:
        return "", None

    url = f"https://api.openalex.org/works/https://doi.org/{urllib.parse.quote(doi, safe='/')}"
    params = {}
    if os.getenv("OPENALEX_MAILTO"):
        params["mailto"] = os.environ["OPENALEX_MAILTO"]

    response = session.get(url, params=params, timeout=30)
    if response.status_code == 404:
        return "", None
    response.raise_for_status()
    payload = response.json()
    return (
        reconstruct_openalex_abstract(payload.get("abstract_inverted_index")),
        year_value(payload.get("publication_year")),
    )


def fetch_crossref_abstract(doi: str) -> tuple[str, int | None]:
    if not doi:
        return "", None

    params = {}
    if os.getenv("CROSSREF_MAILTO"):
        params["mailto"] = os.environ["CROSSREF_MAILTO"]

    response = session.get(
        f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}",
        params=params,
        timeout=30,
    )
    if response.status_code == 404:
        return "", None
    response.raise_for_status()
    message = response.json().get("message", {})

    abstract = clean_text(message.get("abstract"))
    year = None
    for key in ("published-print", "published-online", "created"):
        parts = message.get(key, {}).get("date-parts", [])
        if parts and parts[0]:
            year = year_value(parts[0][0])
            if year:
                break
    return abstract, year


def fetch_semantic_scholar(url: str) -> tuple[str, int | None]:
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    if not api_key or not url:
        return "", None

    encoded = urllib.parse.quote(f"URL:{url}", safe="")
    response = session.get(
        f"https://api.semanticscholar.org/graph/v1/paper/{encoded}",
        params={"fields": "title,abstract,year"},
        headers={"x-api-key": api_key},
        timeout=30,
    )
    if response.status_code in {404, 429}:
        return "", None
    response.raise_for_status()
    payload = response.json()
    return clean_text(payload.get("abstract")), year_value(payload.get("year"))


def enrich_abstracts(records: list[dict[str, Any]], offline: bool = False) -> None:
    cache = load_json(ABSTRACT_CACHE_PATH, {})

    for index, record in enumerate(records, start=1):
        key = record["paper_key"]
        cached = cache.get(key, {})

        if cached.get("abstract") and (offline or cached.get("source") != "catalogue summary"):
            record["abstract"] = cached["abstract"]
            record["abstract_source"] = cached.get("source", "cache")
            if not record.get("year"):
                record["year"] = year_value(cached.get("year"))
            continue

        if record.get("abstract"):
            cache[key] = {
                "abstract": record["abstract"],
                "source": record.get("abstract_source") or "catalogue",
                "year": record.get("year"),
            }
            continue

        abstract = ""
        source = ""
        discovered_year = None
        arxiv_id = extract_arxiv_id(record["paper_url"])
        doi = extract_doi(record["paper_url"])

        attempts = []
        if offline:
            attempts = []
        elif arxiv_id:
            attempts.append(("arXiv", lambda: fetch_arxiv_abstract(arxiv_id)))
        if doi and not offline:
            attempts.append(("Crossref", lambda: fetch_crossref_abstract(doi)))
            attempts.append(("OpenAlex", lambda: fetch_openalex_by_doi(doi)))
        if not offline:
            attempts.append(
                ("Semantic Scholar", lambda: fetch_semantic_scholar(record["paper_url"]))
            )

        for source_name, operation in attempts:
            try:
                candidate_abstract, candidate_year = operation()
                if candidate_abstract:
                    abstract = candidate_abstract
                    source = source_name
                    discovered_year = candidate_year
                    break
            except requests.RequestException as exc:
                print(f"[abstract] {source_name} failed for {record['title']}: {exc}")

        if not abstract:
            # Keep the paper in the map, but mark that the embedding is based on
            # catalogue text rather than a primary-source abstract.
            abstract = clean_text(
                " ".join(
                    part
                    for part in [
                        record["title"],
                        record.get("summary", ""),
                        record.get("tasks", ""),
                        record.get("modalities", ""),
                    ]
                    if part
                )
            )
            source = "catalogue summary"

        record["abstract"] = abstract
        record["abstract_source"] = source
        if not record.get("year"):
            record["year"] = discovered_year

        cache[key] = {
            "abstract": abstract,
            "source": source,
            "year": record.get("year"),
        }

        if index % 20 == 0:
            dump_json(ABSTRACT_CACHE_PATH, cache)

        time.sleep(0.15)

    dump_json(ABSTRACT_CACHE_PATH, cache)


def chunks(values: list[Any], size: int) -> Iterable[list[Any]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def embedding_text(record: dict[str, Any]) -> str:
    return clean_text(f"{record['title']}\n\n{record['abstract']}")[:24000]


def tfidf_fallback(texts: list[str]) -> np.ndarray:
    vectorizer = TfidfVectorizer(
        stop_words="english",
        max_features=2048,
        ngram_range=(1, 2),
        min_df=1,
    )
    matrix = vectorizer.fit_transform(texts)
    dense = matrix.toarray().astype(np.float32)
    return normalize(dense)


def create_embeddings(
    records: list[dict[str, Any]],
    allow_tfidf_fallback: bool,
    batch_size: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    model = (os.getenv("EMBEDDING_MODEL") or "text-embedding-3-small").strip()
    api_key = (
        os.getenv("EMBEDDING_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("LLM_BACKEND_AUTH_TOKEN")
        or ""
    ).strip()
    base_url = os.getenv("EMBEDDING_BASE_URL", "").strip()
    texts = [embedding_text(record) for record in records]

    if not api_key:
        if not allow_tfidf_fallback:
            raise RuntimeError(
                "Set EMBEDDING_API_KEY/OPENAI_API_KEY, "
                "or run with --allow-tfidf-fallback for a non-semantic development build."
            )
        print("[embeddings] API configuration absent; using TF-IDF development fallback.")
        return tfidf_fallback(texts), {
            "provider": "local",
            "model": "tfidf-development-fallback",
            "semantic": False,
        }

    from openai import OpenAI

    client_args: dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_args["base_url"] = base_url.rstrip("/")
    client = OpenAI(**client_args)

    cache = load_json(EMBEDDING_CACHE_PATH, {})
    vectors: list[list[float] | None] = [None] * len(records)
    pending_indexes: list[int] = []

    for index, text in enumerate(texts):
        digest = hashlib.sha256(f"{model}\0{text}".encode("utf-8")).hexdigest()
        records[index]["embedding_digest"] = digest
        cached = cache.get(digest)
        if isinstance(cached, list) and cached:
            vectors[index] = cached
        else:
            pending_indexes.append(index)

    for index_batch in chunks(pending_indexes, batch_size):
        input_batch = [texts[index] for index in index_batch]
        response = client.embeddings.create(model=model, input=input_batch)
        ordered = sorted(response.data, key=lambda item: item.index)

        if len(ordered) != len(index_batch):
            raise RuntimeError("Embedding API returned an unexpected batch length.")

        for record_index, item in zip(index_batch, ordered):
            vector = list(item.embedding)
            vectors[record_index] = vector
            cache[records[record_index]["embedding_digest"]] = vector

        dump_json(EMBEDDING_CACHE_PATH, cache)
        time.sleep(0.25)

    array = np.asarray(vectors, dtype=np.float32)
    array = normalize(array)

    return array, {
        "provider": base_url or "default-openai-compatible-endpoint",
        "model": model,
        "semantic": True,
    }


def choose_cluster_count(n_records: int) -> int:
    configured = os.getenv("PAPER_MAP_CLUSTER_COUNT", "").strip()

    if configured:
        try:
            return max(2, min(int(configured), n_records))
        except ValueError:
            print(
                f"[clusters] Invalid PAPER_MAP_CLUSTER_COUNT={configured!r}; "
                "using automatic selection."
            )

    if n_records < 8:
        return max(2, n_records // 2)

    return max(4, min(8, round(math.sqrt(n_records / 4))))


def reduce_embeddings(embeddings: np.ndarray) -> tuple[np.ndarray, str]:
    if len(embeddings) < 3:
        coordinates = np.column_stack(
            [np.arange(len(embeddings), dtype=float), np.zeros(len(embeddings))]
        )
        return coordinates, "identity"

    pca_dimensions = min(50, embeddings.shape[1], max(2, len(embeddings) - 1))
    compact = PCA(n_components=pca_dimensions, random_state=42).fit_transform(embeddings)

    if os.getenv("PAPER_MAP_REDUCTION", "").strip().lower() == "pca":
        return PCA(n_components=2, random_state=42).fit_transform(compact), "pca"

    try:
        import umap

        reducer = umap.UMAP(
            n_components=2,
            n_neighbors=min(15, max(2, len(embeddings) - 1)),
            min_dist=0.12,
            metric="cosine",
            random_state=42,
        )
        return reducer.fit_transform(compact), "umap"
    except ImportError:
        print("[reduction] umap-learn unavailable; using PCA coordinates.")
        return PCA(n_components=2, random_state=42).fit_transform(compact), "pca"


def cluster_label_texts(
    records: list[dict[str, Any]],
    labels: np.ndarray,
) -> tuple[dict[int, str], dict[int, list[str]]]:
    documents = [embedding_text(record) for record in records]
    cluster_documents: dict[int, str] = {}

    for cluster_id in sorted(set(int(value) for value in labels)):
        cluster_documents[cluster_id] = " ".join(
            documents[index]
            for index, value in enumerate(labels)
            if int(value) == cluster_id
        )

    cluster_ids = list(cluster_documents)
    vectorizer = TfidfVectorizer(
        stop_words=sorted(set(ENGLISH_STOP_WORDS) | GENERIC_CLUSTER_TERMS),
        ngram_range=(1, 2),
        max_features=5000,
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9\-]{2,}\b",
    )
    matrix = vectorizer.fit_transform([cluster_documents[cid] for cid in cluster_ids])
    terms = np.asarray(vectorizer.get_feature_names_out())

    names: dict[int, str] = {}
    keywords: dict[int, list[str]] = {}

    for row_index, cluster_id in enumerate(cluster_ids):
        row = matrix.getrow(row_index).toarray().ravel()
        top_indexes = row.argsort()[::-1][:8]
        top_terms = [terms[idx] for idx in top_indexes if row[idx] > 0]
        keywords[cluster_id] = top_terms
        names[cluster_id] = " · ".join(top_terms[:3]) or f"Cluster {cluster_id + 1}"

    return names, keywords
def improve_cluster_names_with_llm(
    records: list[dict[str, Any]],
    labels: np.ndarray,
    fallback_names: dict[int, str],
    keywords: dict[int, list[str]],
) -> dict[int, str]:
    model = os.getenv("CLUSTER_LABEL_MODEL", "").strip()

    if not model:
        print("[clusters] CLUSTER_LABEL_MODEL not configured; using TF-IDF labels.")
        return fallback_names

    api_key = (
        os.getenv("EMBEDDING_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("LLM_BACKEND_AUTH_TOKEN")
        or ""
    ).strip()

    if not api_key:
        print("[clusters] No API key available; using TF-IDF labels.")
        return fallback_names

    base_url = os.getenv("EMBEDDING_BASE_URL", "").strip()

    cluster_descriptions: list[dict[str, Any]] = []

    for cluster_id in sorted(fallback_names):
        member_titles = [
            records[index]["title"]
            for index, value in enumerate(labels)
            if int(value) == cluster_id
        ][:12]

        cluster_descriptions.append(
            {
                "cluster_id": cluster_id,
                "keywords": keywords.get(cluster_id, []),
                "paper_titles": member_titles,
            }
        )

    prompt = f"""
You are naming semantic clusters in a research landscape of Earth-observation,
remote-sensing, geospatial-AI, foundation-model, benchmark, and dataset papers.

Create one concise and distinctive research-theme label for every cluster.

Rules:
- Use 2 to 5 words.
- Use Title Case.
- Make every label unique.
- Describe the scientific or methodological theme.
- Avoid generic labels such as Remote Sensing, Earth Observation,
  Foundation Models, Models, Papers, Data, or Methods by themselves.
- Prefer labels such as:
  Self-Supervised Representation Learning
  Vision-Language Reasoning
  Generative Satellite Imagery
  Multisensor Fusion
  Geospatial Agents
  Benchmarks and Training Datasets
  Urban Mapping and Geolocation

Return only one JSON object mapping cluster IDs to labels.
Example:
{{"0": "Vision-Language Reasoning", "1": "Multisensor Fusion"}}

Clusters:
{json.dumps(cluster_descriptions, ensure_ascii=False, indent=2)}
""".strip()

    try:
        from openai import OpenAI

        client_args: dict[str, Any] = {"api_key": api_key}

        if base_url:
            client_args["base_url"] = base_url.rstrip("/")

        client = OpenAI(**client_args)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You create concise, accurate labels for clusters of "
                        "scientific publications."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )

        content = response.choices[0].message.content or ""
        match = re.search(r"\{.*\}", content, flags=re.S)

        if not match:
            raise ValueError("The cluster-label model did not return a JSON object.")

        generated = json.loads(match.group(0))
        improved: dict[int, str] = {}
        used_labels: set[str] = set()

        for cluster_id in sorted(fallback_names):
            candidate = clean_text(generated.get(str(cluster_id), ""))
            candidate = candidate.strip(" .:-")
            word_count = len(candidate.split())

            if (
                not candidate
                or word_count < 2
                or word_count > 6
                or len(candidate) > 70
                or candidate.lower() in used_labels
            ):
                candidate = fallback_names[cluster_id]

            improved[cluster_id] = candidate
            used_labels.add(candidate.lower())

        print(f"[clusters] Generated readable labels with {model}")
        return improved

    except Exception as exc:
        print(f"[clusters] LLM cluster naming failed: {exc}")
        print("[clusters] Continuing with TF-IDF fallback labels.")
        return fallback_names

def build_output(
    records: list[dict[str, Any]],
    embeddings: np.ndarray,
    embedding_metadata: dict[str, Any],
) -> dict[str, Any]:
    n_clusters = min(choose_cluster_count(len(records)), len(records))
    clusterer = KMeans(n_clusters=n_clusters, random_state=42, n_init=20)
    labels = clusterer.fit_predict(embeddings)
    coordinates, reduction_method = reduce_embeddings(embeddings)
    cluster_names, cluster_keywords = cluster_label_texts(records, labels)
    cluster_names = improve_cluster_names_with_llm(
    records,
    labels,
    cluster_names,
    cluster_keywords,
)
    points = []
    for index, record in enumerate(records):
        cluster_id = int(labels[index])
        points.append(
            {
                "id": record["id"],
                "title": record["title"],
                "paper_url": record["paper_url"],
                "year": record.get("year"),
                "resource_types": record["resource_types"],
                "associated_entries": record["associated_entries"],
                "abstract": record["abstract"],
                "abstract_source": record["abstract_source"],
                "has_primary_abstract": record["abstract_source"] != "catalogue summary",
                "tasks": record.get("tasks", ""),
                "modalities": record.get("modalities", ""),
                "cluster_id": cluster_id,
                "cluster_label": cluster_names[cluster_id],
                "x": round(float(coordinates[index, 0]), 7),
                "y": round(float(coordinates[index, 1]), 7),
            }
        )

    clusters = []
    for cluster_id in sorted(cluster_names):
        member_indexes = [
            index for index, value in enumerate(labels) if int(value) == cluster_id
        ]
        centroid = embeddings[member_indexes].mean(axis=0)
        distances = np.linalg.norm(embeddings[member_indexes] - centroid, axis=1)
        representative_index = member_indexes[int(np.argmin(distances))]
        clusters.append(
            {
                "id": cluster_id,
                "label": cluster_names[cluster_id],
                "keywords": cluster_keywords[cluster_id],
                "size": len(member_indexes),
                "representative_paper_id": records[representative_index]["id"],
            }
        )

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "record_count": len(points),
        "primary_abstract_count": sum(point["has_primary_abstract"] for point in points),
        "embedding": embedding_metadata,
        "dimensionality_reduction": reduction_method,
        "clustering": {
            "method": "kmeans",
            "cluster_count": n_clusters,
            "label_method": (
    "llm-with-tfidf-fallback"
    if os.getenv("CLUSTER_LABEL_MODEL")
    else "tfidf"
),
        },
        "clusters": clusters,
        "points": points,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-tfidf-fallback",
        action="store_true",
        help="Build a lexical development map when no embedding API is configured.",
    )
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip remote abstract retrieval and use catalogue text for a local preview.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    records = collect_papers()
    if not records:
        raise RuntimeError(
            "No paper records found. Ensure data/catalogue.json and "
            "data/benchmarks.json exist and contain paper_url fields."
        )

    print(f"[papers] collected {len(records)} unique paper records")
    enrich_abstracts(records, offline=args.offline)
    primary_count = sum(
        record["abstract_source"] != "catalogue summary" for record in records
    )
    print(f"[abstracts] primary-source abstracts: {primary_count}/{len(records)}")

    embeddings, embedding_metadata = create_embeddings(
        records,
        allow_tfidf_fallback=args.allow_tfidf_fallback,
        batch_size=max(1, args.batch_size),
    )
    output = build_output(records, embeddings, embedding_metadata)
    dump_json(OUTPUT_PATH, output)

    print(
        f"[output] wrote {OUTPUT_PATH.relative_to(ROOT)} with "
        f"{output['record_count']} points and "
        f"{output['clustering']['cluster_count']} clusters"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
