#!/usr/bin/env python3
"""Prove a built frontend is internally consistent — no dangling chunk references.

Code splitting means `index.html` names an entry bundle, that bundle names a
lazy chunk per route, and every one of those names carries a content hash. If a
single file goes missing, or if `index.html` from one build is packaged with the
assets of another, nothing fails until a user clicks the one route whose chunk is
gone — and then it fails as `TypeError: Failed to fetch dynamically imported
module`, which points at React rather than at the build.

This checks the whole reference graph instead, so a mixed or incomplete build is
caught at the stage that produced it. Run it on every copy the pipeline makes:

    frontend/dist  ->  backend/app/static  ->  desktop/resources/backend/app/static

Usage:
    python scripts/verify_frontend_assets.py frontend/dist
    python scripts/verify_frontend_assets.py backend/app/static --compare frontend/dist
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):  # UTF-8 safe on cp1252 consoles
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

# How Vite writes a reference to another chunk. Either rooted at the assets dir
# ("/assets/Foo-hash.js", from index.html and from preload hints) or relative to
# it ("./Foo-hash.js", from inside a chunk).
_ROOTED = re.compile(r"""["'(]\s*(?:\.\.?)?/?assets/([A-Za-z0-9_$.\-]+\.[a-z0-9]+)""")
_RELATIVE = re.compile(r"""["'(]\s*\./([A-Za-z0-9_$.\-]+\.[a-z0-9]+)""")
# A bare, unprefixed filename is only trusted when it carries a content hash,
# so arbitrary strings in the source cannot be mistaken for asset references.
_HASHED = re.compile(r"""["'](([A-Za-z0-9_$.]+)-[A-Za-z0-9_\-]{8,10}\.(?:js|css))["']""")

# Files worth scanning for onward references.
_SCANNABLE = {".js", ".mjs", ".css", ".html"}


def references(path: Path) -> set[str]:
    """Every asset filename `path` points at."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set()
    found = set(_ROOTED.findall(text)) | set(_RELATIVE.findall(text))
    found |= {m[0] for m in _HASHED.findall(text)}
    return {f for f in found if not f.startswith("http")}


def check(root: Path) -> tuple[list[str], dict]:
    problems: list[str] = []
    index = root / "index.html"
    if not index.is_file():
        return [f"{root}: no index.html — this is not a frontend build"], {}

    assets = root / "assets"
    if not assets.is_dir():
        return [f"{root}: no assets/ directory — code-split chunks cannot resolve"], {}

    present = {p.name for p in assets.iterdir() if p.is_file()}
    if not present:
        return [f"{root}/assets: empty"], {}

    # index.html must name at least one entry bundle, or the page renders nothing.
    entry = {r for r in references(index) if r.endswith(".js")}
    if not entry:
        problems.append("index.html references no JavaScript entry bundle")

    # Walk the graph: index.html -> entry -> lazy chunks -> ...
    graph: dict[str, set[str]] = {}
    for f in sorted(assets.iterdir()):
        if f.is_file() and f.suffix.lower() in _SCANNABLE:
            graph[f.name] = references(f)
    graph["index.html"] = references(index)

    dangling: dict[str, set[str]] = {}
    for source, refs in graph.items():
        for ref in refs:
            if ref not in present and not (root / ref).is_file():
                dangling.setdefault(ref, set()).add(source)

    for ref in sorted(dangling):
        via = ", ".join(sorted(dangling[ref])[:3])
        problems.append(
            f"dangling reference '{ref}' (named by {via}) — navigating to that "
            "route would fail with 'Failed to fetch dynamically imported module'"
        )

    chunks = sorted(n for n in present if n.endswith(".js"))
    stats = {"assets": len(present), "js_chunks": len(chunks),
             "referenced": len({r for refs in graph.values() for r in refs}),
             "entry": sorted(entry)}
    return problems, stats


def digests(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*") if p.is_file()
    }


def compare(a: Path, b: Path) -> list[str]:
    """Two copies of the same build must be byte-identical.

    Staging copies the build several times. A partial copy, or a copy made from a
    different build, is exactly the mixed-build failure this guards against.
    """
    da, db = digests(a), digests(b)
    problems = []
    for name in sorted(set(db) - set(da)):
        problems.append(f"{a} is missing '{name}' present in {b}")
    for name in sorted(set(da) - set(db)):
        problems.append(f"{a} has extra '{name}' not in {b}")
    for name in sorted(set(da) & set(db)):
        if da[name] != db[name]:
            problems.append(f"'{name}' differs between {a} and {b} — mixed builds")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("directory", type=Path, help="a frontend build root (holds index.html)")
    ap.add_argument("--compare", type=Path, default=None,
                    help="another copy of the same build; must be byte-identical")
    args = ap.parse_args()

    root: Path = args.directory
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 1

    problems, stats = check(root)
    if stats:
        print(f"{root}: {stats['assets']} assets, {stats['js_chunks']} JS chunks, "
              f"{stats['referenced']} references, entry {stats['entry']}")

    if args.compare:
        if not args.compare.is_dir():
            problems.append(f"--compare directory does not exist: {args.compare}")
        else:
            problems += compare(root, args.compare)

    if problems:
        print(f"\n{len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print("OK: every referenced asset exists")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
