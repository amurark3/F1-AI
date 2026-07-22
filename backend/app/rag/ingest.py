"""
RAG Ingestion Script
====================
Scans the data/raw/ directory for FIA regulation PDFs, splits them into
overlapping text chunks, embeds them, and stores everything in the Postgres
(pgvector) rulebook table on Supabase.

Because the vectors live in Postgres, deploys never rebuild a local vector DB —
run this once (locally or as a one-off) after updating the regulation PDFs.

Usage (run from the backend/ directory, with DATABASE_URL set):
    python -m app.rag.ingest            # skip if the table is already populated
    python -m app.rag.ingest --force    # wipe and re-embed the whole corpus

Expected folder layout:
    backend/data/raw/{2024,2025,2026}/*.pdf

Year is auto-detected from the parent folder name (e.g. "2024").
Document type (Sporting / Technical / Financial) is detected from the filename.
"""

import os
import re
import sys

import structlog
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.rag import pgvector_store

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = "data/raw"    # Root folder containing year sub-directories


def _detect_year(root: str, filename: str) -> str:
    folder_name = os.path.basename(root)
    if folder_name.isdigit() and len(folder_name) == 4:
        return folder_name
    match = re.search(r"20\d{2}", filename)
    return match.group(0) if match else "General"


def _detect_doc_type(filename: str) -> str:
    name_lower = filename.lower()
    if "sporting" in name_lower:
        return "Sporting"
    if "technical" in name_lower:
        return "Technical"
    if "financial" in name_lower:
        return "Financial"
    return "Regulatory"


def collect_chunks() -> list[dict]:
    """Walk the PDF corpus and return chunk dicts ready for pgvector.

    Each chunk: ``{source_year, doc_type, filename, page, content}``.
    """
    chunks: list[dict] = []
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        # Prioritise splitting on article boundaries first.
        separators=["\n\n", "\n", "ARTICLE", " ", ""],
    )

    logger.info("ingest.scanning", path=DATA_DIR)
    for root, _dirs, files in os.walk(DATA_DIR):
        for filename in files:
            if not filename.lower().endswith(".pdf"):
                continue

            year = _detect_year(root, filename)
            doc_type = _detect_doc_type(filename)
            logger.info("ingest.processing", filename=filename, year=year, doc_type=doc_type)

            try:
                raw_docs = PyPDFLoader(os.path.join(root, filename)).load()
                for split in text_splitter.split_documents(raw_docs):
                    # PyPDFLoader tags each doc with a 0-indexed 'page'.
                    page = split.metadata.get("page")
                    chunks.append({
                        "source_year": str(year),
                        "doc_type": doc_type,
                        "filename": filename,
                        "page": page,
                        "content": split.page_content,
                    })
                logger.info("ingest.chunks_added", filename=filename)
            except Exception as exc:
                logger.error("ingest.load_failed", filename=filename, error=str(exc))

    return chunks


def ingest_data(force: bool = False) -> None:
    """Populate the pgvector rulebook table from the PDF corpus.

    Idempotent by default: if the table is already populated it is left alone
    (pass ``force=True`` / ``--force`` to wipe and re-embed after updating PDFs).
    """
    if not pgvector_store.RULEBOOK_ENABLED:
        print("DATABASE_URL is not set — cannot populate the pgvector rulebook.")
        return

    existing = pgvector_store.count()
    if existing > 0 and not force:
        logger.info("ingest.skipped_existing", rows=existing)
        print(f"Rulebook already has {existing} chunks in pgvector — skipping (use --force to rebuild).")
        return

    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        logger.warning("ingest.no_data_dir", path=DATA_DIR)
        return

    chunks = collect_chunks()
    if not chunks:
        logger.warning("ingest.no_pdfs_found", data_dir=DATA_DIR)
        return

    logger.info("ingest.saving", total_chunks=len(chunks))
    written = pgvector_store.replace_all(chunks)
    logger.info("ingest.complete", status="success", rows=written)
    print(f"Ingest complete — {written} rulebook chunks written to pgvector.")


if __name__ == "__main__":
    ingest_data(force="--force" in sys.argv)
