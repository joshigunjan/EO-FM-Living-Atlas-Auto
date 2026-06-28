from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote

import requests
from pypdf import PdfReader

from lib_utils import DATA, arxiv_id_from_url, doi_from_text, dump_json, github_repo_from_url, load_json

CAND_PATH = DATA / "candidates" / "latest-candidates.json"
OUT_PATH = DATA / "candidates" / "latest-candidates.with-metadata.json"
USER_AGENT = "EO-FM-Living-Atlas-Auto/1.0 (metadata enrichment)"
MAX_PDF_PAGES = 8
MAX_PAPER_TEXT_CHARS = 22000
MAX_README_CHARS = 9000


def fetch_arxiv(arxiv_id: str) -> dict:
    url = f"https://export.arxiv.org/api/query?id_list={quote(arxiv_id)}"
    r = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    root = ET.fromstring(r.text)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entry = root.find("a:entry", ns)
    if entry is None:
        return {}
    return {
        "arxiv_id": arxiv_id,
        "arxiv_title": " ".join((entry.findtext("a:title", default="", namespaces=ns) or "").split()),
        "arxiv_summary": " ".join((entry.findtext("a:summary", default="", namespaces=ns) or "").split()),
        "arxiv_published": entry.findtext("a:published", default="", namespaces=ns),
        "arxiv_updated": entry.findtext("a:updated", default="", namespaces=ns),
        "arxiv_authors": [a.findtext("a:name", default="", namespaces=ns) for a in entry.findall("a:author", ns)],
    }


def fetch_arxiv_pdf_text(arxiv_id: str) -> dict:
    """Fetch a bounded amount of arXiv PDF text for LLM extraction.

    This is intentionally capped: the goal is enough evidence for modalities,
    architecture, access notes, and task/benchmark descriptions without trying
    to ingest entire long papers in every scheduled run.
    """
    pdf_url = f"https://arxiv.org/pdf/{quote(arxiv_id)}"
    r = requests.get(pdf_url, timeout=60, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    reader = PdfReader(io.BytesIO(r.content))
    chunks: list[str] = []
    for page in reader.pages[:MAX_PDF_PAGES]:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            chunks.append(" ".join(text.split()))
        if sum(len(c) for c in chunks) >= MAX_PAPER_TEXT_CHARS:
            break
    paper_text = "\n\n".join(chunks)[:MAX_PAPER_TEXT_CHARS]
    return {
        "paper_pdf_url": pdf_url,
        "paper_text_excerpt": paper_text,
        "paper_text_pages_read": min(MAX_PDF_PAGES, len(reader.pages)),
    }


def fetch_crossref(doi: str) -> dict:
    if not doi:
        return {}
    url = f"https://api.crossref.org/works/{quote(doi)}"
    r = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    msg = r.json().get("message", {})
    title = " ".join(msg.get("title", [])[:1])
    abstract = msg.get("abstract", "") or ""
    abstract = re.sub(r"<[^>]+>", " ", abstract)
    return {
        "doi": doi,
        "crossref_title": " ".join(title.split()),
        "crossref_abstract": " ".join(abstract.split())[:5000],
        "crossref_published": msg.get("published-print") or msg.get("published-online") or {},
        "crossref_container_title": " ".join(msg.get("container-title", [])[:1]),
    }


def fetch_github_readme(repo: str) -> dict:
    owner, name = repo.split("/", 1)
    for branch in ["main", "master"]:
        url = f"https://raw.githubusercontent.com/{owner}/{name}/{branch}/README.md"
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
            if r.ok and r.text.strip():
                text = r.text[:MAX_README_CHARS]
                return {"github_repo": repo, "github_readme_excerpt": text, "github_readme_branch": branch}
        except Exception:
            pass
    return {"github_repo": repo}


def main() -> int:
    candidates = load_json(CAND_PATH, [])
    for cand in candidates:
        metadata = cand.get("metadata", {})
        paper = cand.get("paper_url", "")
        raw_text = "\n".join(str(cand.get(k, "")) for k in ["title", "paper_url", "raw_row"])
        raw_text += "\n" + "\n".join(str(ev) for ev in cand.get("source_evidence", []) or [])

        aid = arxiv_id_from_url(paper)
        if aid:
            try:
                metadata.update(fetch_arxiv(aid))
            except Exception as exc:
                metadata["arxiv_error"] = str(exc)
            try:
                metadata.update(fetch_arxiv_pdf_text(aid))
            except Exception as exc:
                metadata["paper_text_error"] = str(exc)

        doi = doi_from_text(paper) or doi_from_text(raw_text)
        if doi:
            try:
                metadata.update(fetch_crossref(doi))
            except Exception as exc:
                metadata["crossref_error"] = str(exc)

        for url_field in ["code_url", "project_url"]:
            repo = github_repo_from_url(cand.get(url_field, ""))
            if repo:
                try:
                    metadata.update(fetch_github_readme(repo))
                except Exception as exc:
                    metadata["github_error"] = str(exc)
                break
        cand["metadata"] = metadata
    dump_json(OUT_PATH, candidates)
    print(f"Metadata fetched for {len(candidates)} candidate entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
