#!/usr/bin/env python3
"""Integrate the semantic Paper map into the current EO-FM Living Atlas repo."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["index.html", "landscape.html", "benchmarks.html", "submit.html", "method.html"]


def add_nav_link(path: Path) -> None:
    if not path.exists():
        print(f"[skip] missing {path.name}")
        return

    text = path.read_text(encoding="utf-8")
    if 'href="paper-map.html"' in text:
        print(f"[skip] navigation already updated in {path.name}")
        return

    anchor = '<a href="landscape.html">Landscape</a>'
    if anchor not in text:
        print(f"[warn] Landscape link not found in {path.name}")
        return

    text = text.replace(
        anchor,
        anchor + '<a href="paper-map.html">Paper map</a>',
        1,
    )
    path.write_text(text, encoding="utf-8")
    print(f"[updated] navigation in {path.name}")


def patch_catalogue_workflow() -> None:
    path = ROOT / ".github" / "workflows" / "sync-upstreams.yml"
    if not path.exists():
        print("[warn] sync-upstreams.yml not found")
        return

    text = path.read_text(encoding="utf-8")
    if 'data/paper-map.json' in text:
        print("[skip] catalogue workflow already ignores paper-map output")
        return

    anchor = '      - "data/benchmarks.csv"\n'
    addition = (
        anchor
        + '      - "data/paper-map.json"\n'
        + '      - "data/paper-map-cache/**"\n'
    )

    if anchor not in text:
        print("[warn] paths-ignore anchor not found in sync-upstreams.yml")
        return

    path.write_text(text.replace(anchor, addition, 1), encoding="utf-8")
    print("[updated] sync-upstreams.yml paths-ignore")


def patch_gitignore() -> None:
    path = ROOT / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    line = "data/paper-map-cache/"
    if line not in text:
        text = text.rstrip() + "\n\n# Semantic paper-map build cache\n" + line + "\n"
        path.write_text(text, encoding="utf-8")
        print("[updated] .gitignore")


def patch_method_page() -> None:
    path = ROOT / "method.html"
    if not path.exists():
        return

    text = path.read_text(encoding="utf-8")
    if "Semantic paper map" in text:
        return

    card = (
        '<article class="panel method-card"><h2>Semantic paper map</h2>'
        '<p>Paper abstracts are embedded, clustered in the original embedding '
        'space, and projected to two dimensions with UMAP. Nearby points indicate '
        'related research themes, not model performance.</p></article>'
    )

    marker = "</section>"
    if marker in text:
        text = text.replace(marker, card + marker, 1)
        path.write_text(text, encoding="utf-8")
        print("[updated] method.html")


def patch_readme() -> None:
    path = ROOT / "README.md"
    if not path.exists():
        return

    text = path.read_text(encoding="utf-8")
    if "## Semantic paper map" in text:
        return

    section = """

## Semantic paper map

The **Paper map** tab visualizes the literature behind the atlas. Abstracts are embedded, clustered in the original embedding space, and projected to two dimensions with UMAP. Nearby points represent semantically related papers. The map is regenerated automatically after successful catalogue updates.

The visualization is exploratory: two-dimensional distances are approximate and do not represent model performance.
"""

    marker = "\n## Contributing\n"
    if marker in text:
        text = text.replace(marker, section + marker, 1)
    else:
        text += section

    path.write_text(text, encoding="utf-8")
    print("[updated] README.md")


for page in PAGES:
    add_nav_link(ROOT / page)

patch_catalogue_workflow()
patch_gitignore()
patch_method_page()
patch_readme()
print("Paper map integration complete.")
