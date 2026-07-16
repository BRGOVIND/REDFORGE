"""Format parsers: raw bytes → canonical dataset shape.

A parsed dataset is one of two *kinds*:
  * ``records`` — ``list[dict]`` (tabular / structured: CSV, JSON, JSONL)
  * ``text``    — ``list[str]``  (line/paragraph oriented: TXT, MD, PDF, DOCX)

Every parser is pure and defensive: malformed input yields the best-effort
records it can plus a note, never an exception that escapes ``parse``. Stdlib
only, except PDF (pypdf, already a dep) and DOCX (python-docx, optional — a clear
error is returned if it is absent rather than crashing).
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any

SUPPORTED_FORMATS = ["csv", "json", "jsonl", "txt", "md", "markdown", "pdf", "docx"]

# Formats that yield structured rows vs. free text.
_RECORD_FORMATS = {"csv", "json", "jsonl"}


class ParseError(Exception):
    """Raised for a genuinely unparseable input (bad encoding, missing lib)."""


def detect_format(filename: str) -> str:
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext == "markdown":
        return "md"
    if ext in SUPPORTED_FORMATS:
        return ext
    return "txt"  # default: treat unknown as plain text


def _decode(data: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Per-format parsers
# ---------------------------------------------------------------------------

def _parse_csv(data: bytes) -> tuple[str, list[Any], list[str]]:
    text = _decode(data)
    reader = csv.DictReader(io.StringIO(text))
    rows = [dict(r) for r in reader]
    cols = list(reader.fieldnames or [])
    return "records", rows, cols


def _parse_jsonl(data: bytes) -> tuple[str, list[Any], list[str]]:
    rows: list[Any] = []
    for line in _decode(data).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            rows.append({"_raw": line})
    return "records", rows, _columns_of(rows)


def _parse_json(data: bytes) -> tuple[str, list[Any], list[str]]:
    try:
        obj = json.loads(_decode(data))
    except ValueError as exc:
        raise ParseError(f"invalid JSON: {exc}") from exc
    if isinstance(obj, list):
        rows = [r if isinstance(r, dict) else {"value": r} for r in obj]
    elif isinstance(obj, dict):
        # A dict of lists (columnar) → rows; else wrap as a single record.
        if obj and all(isinstance(v, list) for v in obj.values()):
            n = max((len(v) for v in obj.values()), default=0)
            rows = [{k: (v[i] if i < len(v) else None) for k, v in obj.items()} for i in range(n)]
        else:
            rows = [obj]
    else:
        rows = [{"value": obj}]
    return "records", rows, _columns_of(rows)


def _parse_text(data: bytes) -> tuple[str, list[Any], list[str]]:
    # One record per non-empty line; whole-doc text is reconstructable by joining.
    lines = [ln for ln in _decode(data).splitlines()]
    return "text", lines, []


def _parse_pdf(data: bytes) -> tuple[str, list[Any], list[str]]:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # noqa: BLE001
        raise ParseError("PDF parsing needs pypdf") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(p.extract_text() or "").strip() for p in reader.pages]
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"could not read PDF: {exc}") from exc
    # One record per page (empty pages preserved as "").
    return "text", pages, []


def _parse_docx(data: bytes) -> tuple[str, list[Any], list[str]]:
    try:
        import docx  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise ParseError(
            "DOCX parsing needs python-docx (pip install python-docx)"
        ) from exc
    try:
        doc = docx.Document(io.BytesIO(data))
        paras = [p.text for p in doc.paragraphs]
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"could not read DOCX: {exc}") from exc
    return "text", paras, []


_PARSERS = {
    "csv": _parse_csv,
    "json": _parse_json,
    "jsonl": _parse_jsonl,
    "txt": _parse_text,
    "md": _parse_text,
    "pdf": _parse_pdf,
    "docx": _parse_docx,
}


def _columns_of(rows: list[Any]) -> list[str]:
    cols: list[str] = []
    for r in rows[:200]:  # sample for column discovery
        if isinstance(r, dict):
            for k in r:
                if k not in cols:
                    cols.append(k)
    return cols


def parse(data: bytes, fmt: str) -> dict:
    """Parse ``data`` as ``fmt``. Returns ``{kind, records, columns, format}``."""
    fmt = "md" if fmt == "markdown" else fmt.lower()
    parser = _PARSERS.get(fmt)
    if parser is None:
        parser = _parse_text
        fmt = "txt"
    kind, records, columns = parser(data)
    return {"kind": kind, "records": records, "columns": columns, "format": fmt}


def records_to_text(records: list[Any], kind: str) -> str:
    """Flatten records back to a text blob (for export / token estimation)."""
    if kind == "text":
        return "\n".join(str(r) for r in records)
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
