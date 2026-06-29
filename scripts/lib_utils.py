from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

URL_RE = re.compile(r"https?://[^\s)\]>'\"]+")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: str | Path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))



def _clean_surrogates(obj):
    """Remove invalid Unicode surrogate characters before writing JSON."""
    if isinstance(obj, str):
        return obj.encode("utf-8", "replace").decode("utf-8")
    if isinstance(obj, list):
        return [_clean_surrogates(x) for x in obj]
    if isinstance(obj, dict):
        return {str(_clean_surrogates(k)): _clean_surrogates(v) for k, v in obj.items()}
    return obj

def dump_json(path: str | Path, obj) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def strip_md(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", text)
    text = re.sub(r"(\*\*|__)(.*?)(\*\*|__)", r"\2", text)
    text = re.sub(r"(\*|_)(.*?)(\*|_)", r"\2", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text).strip(" |\t\n\r")


def slugify(text: str, fallback: str = "entry") -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text or fallback


def normalize_name(text: str) -> str:
    text = strip_md(text).lower()
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"\b(v|version)\s*(\d+(?:\.\d+)*)\b", r"v\2", text)
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def normalize_title(text: str) -> str:
    text = strip_md(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_urls(text: str) -> list[str]:
    if not text:
        return []
    urls = [m.group(2) for m in MD_LINK_RE.finditer(text)]
    urls += URL_RE.findall(text)
    cleaned = []
    for u in urls:
        u = u.rstrip(".,;:!")
        if u not in cleaned:
            cleaned.append(u)
    return cleaned


def normalize_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip().rstrip("/")
    p = urlparse(url)
    host = p.netloc.lower().replace("www.", "")
    path = re.sub(r"/+$", "", p.path)
    return urlunparse((p.scheme.lower() or "https", host, path, "", "", ""))


def arxiv_id_from_url(url: str) -> str:
    if not url:
        return ""
    u = normalize_url(url)
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5})(?:v\d+)?", u)
    return m.group(1) if m else ""


def doi_from_text(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", text)
    if not m:
        return ""
    return m.group(0).rstrip(".,;)").lower()


def github_repo_from_url(url: str) -> str:
    if not url:
        return ""
    p = urlparse(normalize_url(url))
    if p.netloc != "github.com":
        return ""
    parts = [x for x in p.path.split("/") if x]
    if len(parts) >= 2:
        return f"{parts[0].lower()}/{parts[1].lower()}"
    return ""


def hf_repo_from_url(url: str) -> str:
    if not url:
        return ""
    p = urlparse(normalize_url(url))
    if p.netloc not in {"huggingface.co", "www.huggingface.co"}:
        return ""
    parts = [x for x in p.path.split("/") if x]
    if len(parts) >= 2:
        return f"{parts[0].lower()}/{parts[1].lower()}"
    return ""


def identity_keys(obj: dict) -> list[str]:
    keys = []
    blob = "\n".join(str(obj.get(k, "")) for k in ["name", "title", "paper_url", "code_url", "weights_url", "project_url", "raw_row"])
    for field in ["paper_url", "code_url", "weights_url", "project_url"]:
        url = obj.get(field) or ""
        if not url:
            continue
        aid = arxiv_id_from_url(url)
        if aid:
            keys.append(f"arxiv:{aid}")
        gh = github_repo_from_url(url)
        if gh:
            keys.append(f"github:{gh}")
        hf = hf_repo_from_url(url)
        if hf:
            keys.append(f"hf:{hf}")
        norm = normalize_url(url)
        if field == "paper_url" and norm:
            keys.append(f"paper_url:{norm}")
    doi = doi_from_text(blob)
    if doi:
        keys.append(f"doi:{doi}")
    # De-duplicate while preserving order.
    out = []
    for k in keys:
        if k not in out:
            out.append(k)
    return out


def infer_modality_tags(text: str) -> list[str]:
    t = (text or "").lower()
    pairs = [
        ("hyperspectral", ["hyperspectral", "hsi"]),
        ("multispectral", ["multispectral", "sentinel-2", "landsat", "optical"]),
        ("SAR", ["sar", "synthetic aperture radar", "sentinel-1"]),
        ("LiDAR", ["lidar", "gedi", "icesat"]),
        ("DEM", ["dem", "elevation", "topography"]),
        ("climate", ["climate", "weather", "meteorological", "era5"]),
        ("text", ["language", "caption", "text", "vqa"]),
        ("point cloud", ["point cloud", "3d point"]),
    ]
    tags = []
    for tag, words in pairs:
        if any(w in t for w in words):
            tags.append(tag)
    return tags


def infer_architecture_tags(text: str) -> list[str]:
    t = (text or "").lower()
    pairs = [
        ("Transformer", ["transformer", "vit", "mae", "masked autoencoder"]),
        ("Contrastive", ["contrastive", "clip"]),
        ("Vision-language", ["vision-language", "vlm", "mllm", "llm", "vqa"]),
        ("State-space", ["mamba", "state space", "state-space"]),
        ("Generative", ["diffusion", "generative", "any-to-any", "latent"]),
    ]
    tags = []
    for tag, words in pairs:
        if any(w in t for w in words):
            tags.append(tag)
    return tags


def infer_access(urls: list[str]) -> tuple[str, str]:
    has_code = any(github_repo_from_url(u) for u in urls)
    has_hf = any(hf_repo_from_url(u) for u in urls)
    if has_code and has_hf:
        return "open", "Open source"
    if has_code or has_hf:
        return "partial", "Partial access"
    return "unknown", "Unknown"
