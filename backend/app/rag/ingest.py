"""
RAG Ingestion Script
====================
Scans the data/raw/ directory for FIA regulation PDFs, splits them into
overlapping text chunks, generates vector embeddings, and stores everything
in a local ChromaDB database at data/chroma/.

Usage (run from the backend/ directory):
    python app/rag/ingest.py

Expected folder layout:
    backend/
    └── data/
        └── raw/
            ├── 2024/
            │   ├── Sporting_Regulations.pdf
            │   ├── Technical_Regulations.pdf
            │   └── Financial_Regulations.pdf
            ├── 2025/
            │   └── ...
            └── 2026/
                └── ...

Year is auto-detected from the parent folder name (e.g. "2024").
Document type (Sporting / Technical / Financial) is detected from the filename.

The script wipes and rebuilds the database each run to prevent stale rule
versions (e.g. Issue 4 vs Issue 5 of the same regulation document).

After running, restart the backend so the consult_rulebook tool picks up
the updated database.
"""

import os
import shutil
import re
import structlog
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = "data/raw"    # Root folder containing year sub-directories
DB_PATH = "data/chroma"  # Output path for the ChromaDB vector database


def ingest_data():
    """
    Main ingestion routine.

    Steps:
      1. Wipe the existing ChromaDB database (clean slate to avoid conflicts).
      2. Walk DATA_DIR and process every .pdf file found.
      3. Auto-detect year and document type from folder/filename.
      4. Split each PDF into overlapping 1 000-token chunks.
      5. Tag each chunk with metadata (year, type, filename).
      6. Embed all chunks with sentence-transformers/all-MiniLM-L6-v2.
      7. Persist to ChromaDB at DB_PATH.
    """

    # Step 1 — Clean slate
    # Wiping ensures old document versions don't mix with new ones.
    if os.path.exists(DB_PATH):
        shutil.rmtree(DB_PATH)
        logger.info("ingest.cleared_database", path=DB_PATH)

    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        logger.info("ingest.created_data_dir", path=DATA_DIR)
        return

    all_docs = []
    total_files = 0

    # Step 2 — Walk directory tree
    logger.info("ingest.scanning", path=DATA_DIR)

    for root, dirs, files in os.walk(DATA_DIR):
        for filename in files:
            if not filename.lower().endswith(".pdf"):
                continue

            total_files += 1
            file_path = os.path.join(root, filename)

            # Step 3a — Detect year
            # Prefer the direct parent folder name (e.g. "2025").
            # Fall back to a year pattern in the filename itself.
            folder_name = os.path.basename(root)
            if folder_name.isdigit() and len(folder_name) == 4:
                year = folder_name
            else:
                year_match = re.search(r"20\d{2}", filename)
                year = year_match.group(0) if year_match else "General"

            # Step 3b — Detect document type from filename keywords
            doc_type = "Regulatory"
            name_lower = filename.lower()
            if "sporting" in name_lower:
                doc_type = "Sporting"
            elif "technical" in name_lower:
                doc_type = "Technical"
            elif "financial" in name_lower:
                doc_type = "Financial"

            logger.info("ingest.processing", filename=filename, year=year, doc_type=doc_type)

            try:
                # Step 4 — Load and split
                loader = PyPDFLoader(file_path)
                raw_docs = loader.load()

                # chunk_overlap=200 ensures sentences spanning chunk boundaries
                # are captured in at least one chunk.
                text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=1000,
                    chunk_overlap=200,
                    # Prioritise splitting on article boundaries first.
                    separators=["\n\n", "\n", "ARTICLE", " ", ""],
                )

                splits = text_splitter.split_documents(raw_docs)

                # Step 5 — Tag metadata on every chunk
                for doc in splits:
                    doc.metadata["source_year"] = str(year)
                    doc.metadata["type"] = doc_type
                    doc.metadata["filename"] = filename
                    # 'source' is used by LangChain retrievers for citation display.
                    doc.metadata["source"] = filename

                all_docs.extend(splits)
                logger.info("ingest.chunks_added", filename=filename, chunks=len(splits))

            except Exception as e:
                logger.error("ingest.load_failed", filename=filename, error=str(e))

    # Step 6 & 7 — Embed and persist
    if all_docs:
        logger.info("ingest.saving", total_chunks=len(all_docs), path=DB_PATH)
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

        Chroma.from_documents(
            documents=all_docs,
            embedding=embeddings,
            persist_directory=DB_PATH,
        )
        logger.info("ingest.complete", status="success")
    else:
        logger.warning("ingest.no_pdfs_found", data_dir=DATA_DIR)


if __name__ == "__main__":
    ingest_data()
