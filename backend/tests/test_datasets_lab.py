"""Dataset Lab — parsers, analysis, cleaning, splitting (pure) + the full
API lifecycle (import → preview → analyze → clean → version → restore → split →
export) and the dataset-aware Assistant. All offline; no runtime/provider."""
from __future__ import annotations

import io
import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.datasets_lab import analysis, cleaning, parsers, splitting
from app.db.database import Base


# -- pure units -------------------------------------------------------------

def test_parse_csv_json_jsonl_txt():
    csv_bytes = b"prompt,answer\nhi,hello\nbye,goodbye\n"
    p = parsers.parse(csv_bytes, "csv")
    assert p["kind"] == "records" and p["columns"] == ["prompt", "answer"]
    assert len(p["records"]) == 2

    j = parsers.parse(b'[{"a":1},{"a":2}]', "json")
    assert j["kind"] == "records" and len(j["records"]) == 2

    jl = parsers.parse(b'{"x":1}\n{"x":2}\n', "jsonl")
    assert len(jl["records"]) == 2

    t = parsers.parse(b"line one\nline two\n", "txt")
    assert t["kind"] == "text" and t["records"] == ["line one", "line two"]


def test_detect_format():
    assert parsers.detect_format("a.CSV") == "csv"
    assert parsers.detect_format("a.jsonl") == "jsonl"
    assert parsers.detect_format("a.markdown") == "md"
    assert parsers.detect_format("a.unknown") == "txt"


def test_analysis_finds_issues_and_scores():
    records = [
        {"text": "hello world"},
        {"text": "hello world"},   # duplicate
        {"text": ""},              # empty
        {"text": "  spaced  "},    # formatting
    ]
    r = analysis.analyze(records, "records", ["text"], 123)
    assert r["issues"]["duplicates"] == 1
    assert r["issues"]["empty_records"] == 1
    assert 0 <= r["score"] <= 100
    assert r["statistics"]["record_count"] == 4
    assert r["grade"] in {"excellent", "good", "fair", "poor"}


def test_cleaning_is_pure_and_reversible():
    records = [{"t": "a"}, {"t": "a"}, {"t": ""}, {"t": " b "}]
    cleaned, notes = cleaning.clean(records, ["remove_duplicates", "remove_empty", "trim_whitespace"])
    # original untouched
    assert records[3]["t"] == " b "
    texts = [r["t"] for r in cleaned]
    assert "b" in texts and "" not in texts
    assert len(cleaned) < len(records)
    assert notes


def test_split_is_deterministic_and_sums():
    records = list(range(100))
    a = splitting.split(records, train=0.8, val=0.1, test=0.1, seed=1)
    b = splitting.split(records, train=0.8, val=0.1, test=0.1, seed=1)
    assert a["statistics"] == b["statistics"]
    s = a["statistics"]
    assert s["train"] + s["validation"] + s["test"] == 100


# -- API lifecycle ----------------------------------------------------------

@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    fac = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = fac()
    yield session
    await session.close()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    from app.main import app
    from app.db.database import get_db
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def _import(client, name="ds.csv", content=b"text\nhi\nhi\n\n bye \n"):
    files = {"file": (name, io.BytesIO(content), "text/csv")}
    return (await client.post("/api/datasets/import", files=files, data={"name": "Test DS"})).json()


@pytest.mark.asyncio
async def test_import_preview_analyze_clean_version_restore(client):
    ds = await _import(client)
    did = ds["id"]
    assert ds["record_count"] == 3  # "hi","hi","", " bye " → csv rows (header 'text')
    assert ds["current_version"] == 1

    # preview + pagination + search
    pv = (await client.get(f"/api/datasets/{did}/preview", params={"limit": 2})).json()
    assert pv["total"] == 3 and len(pv["rows"]) == 2
    found = (await client.get(f"/api/datasets/{did}/preview", params={"search": "bye"})).json()
    assert found["total"] == 1

    # analyze
    rep = (await client.get(f"/api/datasets/{did}/analyze")).json()
    assert rep["issues"]["duplicates"] >= 1
    assert 0 <= rep["score"] <= 100

    # clean (preview only — no new version)
    prev = (await client.post(f"/api/datasets/{did}/clean",
            json={"operations": ["remove_duplicates", "remove_empty"], "save": False})).json()
    assert prev["saved"] is False
    assert (await client.get(f"/api/datasets/{did}")).json()["current_version"] == 1

    # clean + save → new version
    saved = (await client.post(f"/api/datasets/{did}/clean",
             json={"operations": ["remove_duplicates", "remove_empty"], "save": True})).json()
    assert saved["saved"] is True
    d2 = (await client.get(f"/api/datasets/{did}")).json()
    assert d2["current_version"] == 2 and d2["record_count"] < 3

    # versions + restore (restore makes a NEW version, never overwrites)
    versions = (await client.get(f"/api/datasets/{did}/versions")).json()
    assert len(versions) == 2
    restored = (await client.post(f"/api/datasets/{did}/restore", json={"version": 1})).json()
    assert restored["current_version"] == 3
    assert restored["record_count"] == 3  # v1 content back

    # compare v1 vs v2 — a removed duplicate shows as a negative record-count delta
    # (distinct-content sets are unchanged, so removed==0; that is correct).
    cmp = (await client.get(f"/api/datasets/{did}/compare", params={"a": 1, "b": 2})).json()
    assert cmp["delta"] < 0
    assert cmp["count_a"] == 3 and cmp["count_b"] < 3


@pytest.mark.asyncio
async def test_split_duplicate_export(client):
    ds = await _import(client, content=b"text\n" + b"\n".join(f"row{i}".encode() for i in range(20)))
    did = ds["id"]
    sp = (await client.post(f"/api/datasets/{did}/split",
          json={"train": 0.7, "val": 0.2, "test": 0.1})).json()
    s = sp["statistics"]
    assert s["train"] + s["validation"] + s["test"] == s["total"]

    dup = (await client.post(f"/api/datasets/{did}/duplicate")).json()
    assert dup["id"] != did and dup["name"].endswith("(copy)")

    export = await client.get(f"/api/datasets/{did}/export", params={"fmt": "jsonl"})
    assert export.status_code == 200 and export.text.strip()


@pytest.mark.asyncio
async def test_dataset_attaches_to_project_and_lists(client):
    proj = (await client.post("/api/projects", json={"name": "P"})).json()
    files = {"file": ("d.jsonl", io.BytesIO(b'{"a":1}\n{"a":2}\n'), "application/json")}
    ds = (await client.post("/api/datasets/import", files=files,
          data={"name": "PD", "project_id": proj["id"]})).json()
    assert ds["project_id"] == proj["id"]
    listed = (await client.get("/api/datasets", params={"project_id": proj["id"]})).json()
    assert len(listed) == 1 and listed[0]["id"] == ds["id"]


@pytest.mark.asyncio
async def test_assistant_answers_from_dataset_metadata(client):
    ds = await _import(client)
    r = (await client.post("/api/assistant/ask",
         json={"question": "how many duplicates exist?", "dataset_id": ds["id"]})).json()
    assert "duplicate" in r["answer"].lower()
    assert r["sources"][0]["title"].startswith("Dataset")


@pytest.mark.asyncio
async def test_import_unsupported_and_404s(client):
    # 404 on unknown dataset
    assert (await client.get("/api/datasets/nope")).status_code == 404
    assert (await client.get("/api/datasets/nope/preview")).status_code == 404
    # formats endpoint
    fmts = (await client.get("/api/datasets/formats")).json()["formats"]
    assert "csv" in fmts and "pdf" in fmts
