"""Tests for app.rag.ingest — the one-shot FIA PDF → pgvector loader.

This script is destructive: :func:`ingest_data` truncates the live rulebook
table before re-inserting. The risks it carries are therefore (a) wiping a
populated corpus when nobody asked for a rebuild, and (b) wiping it and then
failing to refill because the PDFs were unreadable. The idempotence guard and
the ordering of the "no data dir" / "no chunks" early returns are what stand
between a bad run and an empty rulebook in production.

The second risk is metadata: every chunk is attributed to a season and a
regulation category derived from the file path, and a wrong attribution surfaces
as the assistant quoting the wrong year's rules.

``PyPDFLoader`` and the pgvector store are both faked — no PDF is parsed and no
connection is opened.
"""

from __future__ import annotations

import pytest

from app.rag import ingest


class _FakeSplit:
    """Minimal LangChain Document stand-in as returned by the text splitter."""

    def __init__(self, page_content: str, page: int | None = 0) -> None:
        self.page_content = page_content
        self.metadata = {"page": page} if page is not None else {}


def _install_loader(monkeypatch, docs_by_file: dict[str, list], failures: tuple[str, ...] = ()):
    """Replace ``PyPDFLoader`` with a lookup over pre-baked page documents."""
    import os

    class _FakeLoader:
        def __init__(self, path: str) -> None:
            self.name = os.path.basename(path)

        def load(self):
            if self.name in failures:
                raise OSError(f"cannot read {self.name}")
            return docs_by_file[self.name]

    monkeypatch.setattr(ingest, "PyPDFLoader", _FakeLoader)


def _make_corpus(tmp_path, **files: str):
    """Create ``data/raw`` with the named files and point DATA_DIR at it."""
    root = tmp_path / "data" / "raw"
    for relative_path, body in files.items():
        target = root / relative_path.replace("__", "/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    return root


# ---------------------------------------------------------------------------
# Metadata detection
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("root", "filename", "expected"),
    [
        ("/corpus/data/raw/2026", "fia_sporting.pdf", "2026"),  # folder wins
        ("/corpus/data/raw/2026", "2024_sporting.pdf", "2026"),  # folder beats filename
        ("/corpus/data/raw", "2024_sporting_regs.pdf", "2024"),  # falls back to filename
        ("/corpus/data/raw/archive", "sporting.pdf", "General"),  # neither carries a year
        ("/corpus/data/raw/202", "sporting.pdf", "General"),  # a 3-digit folder is not a season
        ("/corpus/data/raw/20264", "sporting.pdf", "General"),  # nor a 5-digit one
        ("/corpus/data/raw", "1998_sporting.pdf", "General"),  # pre-2000 is outside the pattern
    ],
)
def test_detect_year_prefers_the_folder_then_the_filename(root, filename, expected):
    assert ingest._detect_year(root, filename) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("2026_FIA_Sporting_Regulations.pdf", "Sporting"),
        ("2026_fia_technical_regulations.pdf", "Technical"),
        ("2026-FINANCIAL-regulations.pdf", "Financial"),
        ("2026_appendix_L.pdf", "Regulatory"),
    ],
)
def test_detect_doc_type_classifies_by_filename_case_insensitively(filename, expected):
    assert ingest._detect_doc_type(filename) == expected


# ---------------------------------------------------------------------------
# collect_chunks()
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_collect_chunks_attributes_every_chunk_to_its_season_and_category(tmp_path, monkeypatch):
    root = _make_corpus(
        tmp_path,
        **{"2026__2026_sporting.pdf": "x", "2025__2025_technical.pdf": "y"},
    )
    monkeypatch.setattr(ingest, "DATA_DIR", str(root))
    _install_loader(
        monkeypatch,
        {
            "2026_sporting.pdf": [_FakeSplit("Article 1. Pit lane speed limit.", page=0)],
            "2025_technical.pdf": [_FakeSplit("Article 3. Aerodynamic components.", page=7)],
        },
    )

    chunks = ingest.collect_chunks()

    by_file = {c["filename"]: c for c in chunks}
    assert by_file["2026_sporting.pdf"]["source_year"] == "2026"
    assert by_file["2026_sporting.pdf"]["doc_type"] == "Sporting"
    assert by_file["2025_technical.pdf"]["source_year"] == "2025"
    assert by_file["2025_technical.pdf"]["doc_type"] == "Technical"
    assert by_file["2025_technical.pdf"]["page"] == 7


@pytest.mark.integration
def test_collect_chunks_ignores_non_pdf_files(tmp_path, monkeypatch):
    root = _make_corpus(tmp_path, **{"2026__notes.txt": "x", "2026__README.md": "y"})
    monkeypatch.setattr(ingest, "DATA_DIR", str(root))
    _install_loader(monkeypatch, {})

    assert ingest.collect_chunks() == []


@pytest.mark.integration
def test_collect_chunks_accepts_uppercase_pdf_extensions(tmp_path, monkeypatch):
    root = _make_corpus(tmp_path, **{"2026__SPORTING.PDF": "x"})
    monkeypatch.setattr(ingest, "DATA_DIR", str(root))
    _install_loader(monkeypatch, {"SPORTING.PDF": [_FakeSplit("Article 1.")]})

    assert len(ingest.collect_chunks()) == 1


@pytest.mark.integration
def test_collect_chunks_splits_long_documents_into_overlapping_chunks(tmp_path, monkeypatch):
    root = _make_corpus(tmp_path, **{"2026__2026_sporting.pdf": "x"})
    monkeypatch.setattr(ingest, "DATA_DIR", str(root))
    # Well over the 1000-character chunk size, so the real splitter must divide it.
    body = "\n\n".join(f"ARTICLE {n}. " + ("regulation text " * 20) for n in range(12))
    _install_loader(monkeypatch, {"2026_sporting.pdf": [_FakeSplit(body)]})

    chunks = ingest.collect_chunks()

    assert len(chunks) > 1
    assert all(len(c["content"]) <= 1000 for c in chunks)


@pytest.mark.integration
def test_collect_chunks_survives_an_unreadable_pdf(tmp_path, monkeypatch):
    root = _make_corpus(tmp_path, **{"2026__broken.pdf": "x", "2026__good_sporting.pdf": "y"})
    monkeypatch.setattr(ingest, "DATA_DIR", str(root))
    _install_loader(
        monkeypatch,
        {"good_sporting.pdf": [_FakeSplit("Article 1.")]},
        failures=("broken.pdf",),
    )

    chunks = ingest.collect_chunks()

    # One bad file must not cost us the rest of the corpus.
    assert [c["filename"] for c in chunks] == ["good_sporting.pdf"]


@pytest.mark.integration
def test_collect_chunks_records_a_missing_page_number_as_none(tmp_path, monkeypatch):
    root = _make_corpus(tmp_path, **{"2026__2026_sporting.pdf": "x"})
    monkeypatch.setattr(ingest, "DATA_DIR", str(root))
    _install_loader(monkeypatch, {"2026_sporting.pdf": [_FakeSplit("Article 1.", page=None)]})

    assert ingest.collect_chunks()[0]["page"] is None


# ---------------------------------------------------------------------------
# ingest_data()
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ingest_data_refuses_to_run_without_a_database(monkeypatch, capsys):
    monkeypatch.setattr(ingest.pgvector_store, "RULEBOOK_ENABLED", False)
    monkeypatch.setattr(
        ingest.pgvector_store, "replace_all", lambda _chunks: pytest.fail("must not write without DATABASE_URL")
    )

    ingest.ingest_data()

    assert "DATABASE_URL is not set" in capsys.readouterr().out


@pytest.mark.unit
def test_ingest_data_leaves_a_populated_table_alone_by_default(monkeypatch, capsys):
    monkeypatch.setattr(ingest.pgvector_store, "RULEBOOK_ENABLED", True)
    monkeypatch.setattr(ingest.pgvector_store, "count", lambda: 4212)
    monkeypatch.setattr(
        ingest.pgvector_store, "replace_all", lambda _chunks: pytest.fail("an unforced run must never truncate")
    )
    monkeypatch.setattr(ingest, "collect_chunks", lambda: pytest.fail("no PDF parsing on the idempotent path"))

    ingest.ingest_data()

    assert "already has 4212 chunks" in capsys.readouterr().out


@pytest.mark.integration
def test_ingest_data_rebuilds_a_populated_table_when_forced(tmp_path, monkeypatch, capsys):
    root = _make_corpus(tmp_path, **{"2026__2026_sporting.pdf": "x"})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ingest, "DATA_DIR", str(root))
    monkeypatch.setattr(ingest.pgvector_store, "RULEBOOK_ENABLED", True)
    monkeypatch.setattr(ingest.pgvector_store, "count", lambda: 4212)
    _install_loader(monkeypatch, {"2026_sporting.pdf": [_FakeSplit("Article 1. Pit lane.")]})
    written: list[list[dict]] = []
    monkeypatch.setattr(ingest.pgvector_store, "replace_all", lambda chunks: written.append(chunks) or len(chunks))

    ingest.ingest_data(force=True)

    assert [c["content"] for c in written[0]] == ["Article 1. Pit lane."]
    assert "1 rulebook chunks written" in capsys.readouterr().out


@pytest.mark.integration
def test_ingest_data_creates_a_missing_corpus_directory_and_stops(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ingest, "DATA_DIR", "data/raw")
    monkeypatch.setattr(ingest.pgvector_store, "RULEBOOK_ENABLED", True)
    monkeypatch.setattr(ingest.pgvector_store, "count", lambda: 0)
    monkeypatch.setattr(
        ingest.pgvector_store, "replace_all", lambda _chunks: pytest.fail("an empty corpus must not truncate the table")
    )

    ingest.ingest_data()

    assert (tmp_path / "data" / "raw").is_dir()


@pytest.mark.integration
def test_ingest_data_does_not_truncate_when_no_pdfs_were_found(tmp_path, monkeypatch):
    root = _make_corpus(tmp_path, **{"2026__notes.txt": "x"})
    monkeypatch.setattr(ingest, "DATA_DIR", str(root))
    monkeypatch.setattr(ingest.pgvector_store, "RULEBOOK_ENABLED", True)
    monkeypatch.setattr(ingest.pgvector_store, "count", lambda: 0)
    monkeypatch.setattr(
        ingest.pgvector_store,
        "replace_all",
        lambda _chunks: pytest.fail("truncating on an empty scan would wipe the live corpus"),
    )
    _install_loader(monkeypatch, {})

    ingest.ingest_data()


@pytest.mark.integration
def test_ingest_data_populates_an_empty_table_without_force(tmp_path, monkeypatch, capsys):
    root = _make_corpus(tmp_path, **{"2026__2026_financial.pdf": "x"})
    monkeypatch.setattr(ingest, "DATA_DIR", str(root))
    monkeypatch.setattr(ingest.pgvector_store, "RULEBOOK_ENABLED", True)
    monkeypatch.setattr(ingest.pgvector_store, "count", lambda: 0)
    _install_loader(monkeypatch, {"2026_financial.pdf": [_FakeSplit("Article 2. Cost cap.")]})
    monkeypatch.setattr(ingest.pgvector_store, "replace_all", len)

    ingest.ingest_data()

    assert "Ingest complete — 1 rulebook chunks written to pgvector." in capsys.readouterr().out
