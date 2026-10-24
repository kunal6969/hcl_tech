"""
ingest_docs.py — Document parsing and ingestion for the hospital KB (R11).

Accepts PDF, Markdown, and plain text files.
Splits into sections/chunks and stores in ChromaDB via app.rag.index.

Called by:
  POST /admin/ingest  (HTTP endpoint)
  scripts/seed_docs.py (initial knowledge base seeding)
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Document parsing
# ---------------------------------------------------------------------------

def _parse_pdf(path: Path) -> str:
    """Extract text from a PDF file using pypdf."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        return f"[PDF parse error: {e}]"


def _parse_markdown(path: Path) -> str:
    """Read markdown/text file as-is."""
    return path.read_text(encoding="utf-8", errors="replace")


def _split_into_chunks(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """
    Split text into overlapping chunks for ChromaDB.

    Strategy:
    1. Try to split on double newlines (paragraph breaks) first
    2. Fall back to fixed-size character windows with overlap
    """
    # Normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text.strip())

    # Split on paragraph breaks
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= chunk_size:
            current = f"{current}\n\n{para}".strip()
        else:
            if current:
                chunks.append(current)
            # If a single paragraph is too long, split by sentences
            if len(para) > chunk_size:
                sentences = re.split(r"(?<=[.!?])\s+", para)
                cur_sent = ""
                for sent in sentences:
                    if len(cur_sent) + len(sent) + 1 <= chunk_size:
                        cur_sent = f"{cur_sent} {sent}".strip()
                    else:
                        if cur_sent:
                            chunks.append(cur_sent)
                        cur_sent = sent
                if cur_sent:
                    current = cur_sent
            else:
                current = para

    if current:
        chunks.append(current)

    return chunks if chunks else [text[:chunk_size]]


# ---------------------------------------------------------------------------
# Main ingest function
# ---------------------------------------------------------------------------

def ingest_document(
    file_path: Path,
    doc_name: str,
    authority: str = "hospital_policy",
    version: str = "1.0",
    effective_date: str = "2026-01-01",
    section: str = "General",
) -> dict[str, Any]:
    """
    Parse a document and add its chunks to the ChromaDB knowledge base.

    This is called by:
      - POST /admin/ingest (live ingestion, R11)
      - scripts/seed_docs.py (initial KB seeding)

    Args:
        file_path: Path to the document file (PDF, .md, .txt).
        doc_name: Human-readable document name (used in citations).
        authority: "government_regulation" | "clinical_guideline" | "hospital_policy"
        version: Version string, e.g. "2.1"
        effective_date: ISO date when this document becomes effective.
        section: Section/chapter name (used in citations).

    Returns:
        {"success": bool, "doc_id": str, "chunks_added": int, "message": str}
    """
    from app.rag.index import add_chunks

    # Parse file based on extension
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        text = _parse_pdf(file_path)
    elif suffix in (".md", ".txt", ".markdown"):
        text = _parse_markdown(file_path)
    else:
        # Try as text by default
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"success": False, "doc_id": "", "chunks_added": 0, "message": f"Cannot read file: {e}"}

    if not text.strip():
        return {"success": False, "doc_id": "", "chunks_added": 0, "message": "Document appears to be empty"}

    # Generate a stable doc_id from the name + version
    doc_id = hashlib.md5(f"{doc_name}-{version}".encode()).hexdigest()[:12]

    # Split into chunks
    chunks = _split_into_chunks(text)

    # Build metadata for each chunk (same for all chunks of this document)
    ingested_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "doc": doc_name,
        "section": section,
        "version": version,
        "effective_date": effective_date,
        "authority": authority,
        "status": "active",
        "ingested_at": ingested_at,
    }
    metadatas = [metadata.copy() for _ in chunks]

    try:
        ids = add_chunks(chunks, metadatas, doc_id_prefix=doc_id)
    except Exception as e:
        return {"success": False, "doc_id": doc_id, "chunks_added": 0, "message": f"ChromaDB error: {e}"}

    return {
        "success": True,
        "doc_id": doc_id,
        "chunks_added": len(ids),
        "message": f"Ingested '{doc_name}' ({len(ids)} chunks, version {version}, effective {effective_date})",
    }
