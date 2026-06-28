from __future__ import annotations

import re
from pathlib import Path

from lib_utils import DATA, dump_json, extract_urls, load_json, normalize_url, slugify, strip_md

RAW_DIR = DATA / "upstream_raw"
OUT_PATH = DATA / "parsed" / "upstream_records.json"
SNAPSHOT_CURRENT = DATA / "upstream_snapshot.current.json"


def split_md_row(line: str) -> list[str]:
    line = line.strip()
    if not (line.startswith("|") and line.endswith("|")):
        return []
    parts = []
    cell = ""
    in_link = 0
    escaped = False
    for ch in line[1:-1]:
        if escaped:
            cell += ch
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            cell += ch
            continue
        if ch == "[":
            in_link += 1
        elif ch == "]" and in_link:
            in_link -= 1
        if ch == "|" and not in_link:
            parts.append(cell.strip())
            cell = ""
        else:
            cell += ch
    parts.append(cell.strip())
    return parts


def is_separator(cells: list[str]) -> bool:
    if not cells:
        return False
    return all(re.fullmatch(r":?-{2,}:?", c.strip()) for c in cells)


def header_index(headers: list[str], candidates: list[str]) -> int | None:
    lower = [strip_md(h).lower() for h in headers]
    for cand in candidates:
        for i, h in enumerate(lower):
            if cand in h:
                return i
    return None


def first_url(cell: str, allow_domains: tuple[str, ...] | None = None) -> str:
    urls = extract_urls(cell)
    if not allow_domains:
        return urls[0] if urls else ""
    for u in urls:
        if any(domain in u.lower() for domain in allow_domains):
            return u
    return ""


def infer_resource_type(section: str, name: str, title: str, raw_row: str) -> str:
    text = f"{section} {name} {title} {raw_row}".lower()
    section_l = (section or "").lower()
    if any(w in section_l for w in ["benchmark", "dataset", "pre-training", "pretraining", "embeddings data"]):
        if "benchmark" in section_l or "bench" in text:
            return "benchmark"
        return "dataset"
    if any(w in text for w in ["benchmark", "bench:", "-bench", "dataset", "pre-training dataset", "pretraining dataset"]):
        return "benchmark_dataset"
    return "model"


def parse_tables(markdown: str, source_id: str, source_meta: dict) -> list[dict]:
    records: list[dict] = []
    lines = markdown.splitlines()
    i = 0
    current_heading = ""
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("#"):
            current_heading = strip_md(line.lstrip("#").strip())
        cells = split_md_row(line)
        if cells and i + 1 < len(lines) and is_separator(split_md_row(lines[i + 1])):
            headers = cells
            j = i + 2
            while j < len(lines):
                row = split_md_row(lines[j])
                if not row or is_separator(row):
                    break
                while len(row) < len(headers):
                    row.append("")
                hmap = {strip_md(headers[k]).lower(): row[k] for k in range(len(headers))}
                name_i = header_index(headers, ["abbreviation", "model", "name"])
                title_i = header_index(headers, ["title", "paper"])
                paper_i = header_index(headers, ["paper", "arxiv", "doi"])
                code_i = header_index(headers, ["code", "weights", "repository", "github"])
                project_i = header_index(headers, ["project", "website", "page", "link", "url", "dataset"])

                name = strip_md(row[name_i]) if name_i is not None else ""
                title = strip_md(row[title_i]) if title_i is not None else ""
                raw_row = " | ".join(row)
                urls = extract_urls(raw_row)
                paper_url = first_url(row[paper_i], ("arxiv.org", "doi.org", "openaccess", "ieee", "springer", "acm", "nature", "sciencedirect")) if paper_i is not None else ""
                if not paper_url:
                    paper_url = next((u for u in urls if "arxiv.org" in u.lower() or "doi.org" in u.lower()), "")
                code_url = first_url(row[code_i], ("github.com", "gitlab", "bitbucket")) if code_i is not None else ""
                weights_url = first_url(row[code_i], ("huggingface.co",)) if code_i is not None else ""
                project_url = first_url(row[project_i]) if project_i is not None else ""

                if not name and title:
                    # Some lists put the model name in the first linked text.
                    name = title.split(":", 1)[0].strip()
                if name or paper_url or code_url:
                    rec = {
                        "record_id": f"{source_id}:{len(records)+1}",
                        "source_id": source_id,
                        "source_name": source_meta.get("name", source_id),
                        "source_repo": source_meta.get("repo", ""),
                        "source_priority": source_meta.get("priority", "medium"),
                        "section": current_heading,
                        "resource_type": infer_resource_type(current_heading, name, title, raw_row),
                        "name": name,
                        "title": title,
                        "paper_url": normalize_url(paper_url),
                        "code_url": normalize_url(code_url),
                        "weights_url": normalize_url(weights_url),
                        "project_url": normalize_url(project_url),
                        "all_urls": [normalize_url(u) for u in urls],
                        "raw_row": raw_row,
                        "raw_columns": hmap,
                    }
                    records.append(rec)
                j += 1
            i = j
        i += 1
    return records


def parse_bullets(markdown: str, source_id: str, source_meta: dict, offset: int) -> list[dict]:
    records = []
    heading = ""
    for line in markdown.splitlines():
        if line.lstrip().startswith("#"):
            heading = strip_md(line.lstrip("#").strip())
            continue
        stripped = line.strip()
        if not re.match(r"^[-*+]\s+", stripped):
            continue
        urls = extract_urls(stripped)
        if not urls:
            continue
        has_paper = any("arxiv.org" in u.lower() or "doi.org" in u.lower() for u in urls)
        has_code = any("github.com" in u.lower() or "huggingface.co" in u.lower() for u in urls)
        if not (has_paper or has_code):
            continue
        label = strip_md(re.sub(r"^[-*+]\s+", "", stripped)).split(" - ")[0].split(":")[0][:120]
        records.append({
            "record_id": f"{source_id}:bullet:{offset + len(records)+1}",
            "source_id": source_id,
            "source_name": source_meta.get("name", source_id),
            "source_repo": source_meta.get("repo", ""),
            "source_priority": source_meta.get("priority", "medium"),
            "section": heading,
            "resource_type": infer_resource_type(heading, label, label, stripped),
            "name": label,
            "title": label,
            "paper_url": normalize_url(next((u for u in urls if "arxiv.org" in u.lower() or "doi.org" in u.lower()), "")),
            "code_url": normalize_url(next((u for u in urls if "github.com" in u.lower()), "")),
            "weights_url": normalize_url(next((u for u in urls if "huggingface.co" in u.lower()), "")),
            "project_url": "",
            "all_urls": [normalize_url(u) for u in urls],
            "raw_row": stripped,
            "raw_columns": {},
        })
    return records


def main() -> int:
    snapshot = load_json(SNAPSHOT_CURRENT, {"sources": {}})
    all_records = []
    seen = set()
    for md_file in sorted(RAW_DIR.glob("*.md")):
        sid = md_file.stem
        meta = snapshot.get("sources", {}).get(sid, {"name": sid})
        if meta.get("status") == "failed":
            continue
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        records = parse_tables(text, sid, meta)
        records += parse_bullets(text, sid, meta, offset=len(records))
        for rec in records:
            sig = (rec.get("source_id"), rec.get("name"), rec.get("paper_url"), rec.get("code_url"), rec.get("weights_url"))
            if sig in seen:
                continue
            seen.add(sig)
            all_records.append(rec)
    dump_json(OUT_PATH, all_records)
    print(f"Parsed {len(all_records)} upstream records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
