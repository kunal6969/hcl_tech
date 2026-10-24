# file: app/rag/ingest_docs.py
"""Document ingest for /ingest and seeding: parse, chunk by section, index, register, upsert/extract rules."""
from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path

from app.data.db import connect, log_ingest
from app.data.registry_io import upsert_rules, upsert_source
from app.data.rule_extract import extract_rules
from app.rag.index import get_index

HEADING = re.compile(r"^\s*(?:#{1,6}\s+(?P<md>.+)|(?:(?:section|clause|article)\s+)?(?P<num>\d+(?:\.\d+){0,3})[.)]?\s+(?P<title>\S.{0,150}))$", re.I)


def read_document(path: str | Path) -> list[dict]:
    """[{page, text}] for pdf/docx/html/md/txt/images. OCR for pages without a text layer when available."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        try:
            import fitz  # PyMuPDF
            pages = []
            with fitz.open(p) as doc:
                for i, page in enumerate(doc, start=1):
                    text = page.get_text()
                    if len(text.strip()) < 25:
                        text = _ocr_png(page.get_pixmap(dpi=200).tobytes("png")) or text
                    pages.append({"page": i, "text": text})
            return pages
        except ImportError:
            from pypdf import PdfReader
            return [{"page": i, "text": pg.extract_text() or ""} for i, pg in enumerate(PdfReader(str(p)).pages, 1)]
    if suffix == ".docx":
        import docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        d = docx.Document(str(p))
        lines = []
        for child in d.element.body.iterchildren():
            if child.tag.endswith("}p"):
                lines.append(Paragraph(child, d).text)
            elif child.tag.endswith("}tbl"):
                for row in Table(child, d).rows:
                    lines.append("| " + " | ".join(c.text.strip() for c in row.cells) + " |")
        return [{"page": 1, "text": "\n".join(lines)}]
    if suffix in (".html", ".htm"):
        raw = p.read_text(errors="ignore")
        try:
            from bs4 import BeautifulSoup
            return [{"page": 1, "text": BeautifulSoup(raw, "html.parser").get_text("\n")}]
        except ImportError:
            return [{"page": 1, "text": re.sub(r"<[^>]+>", "\n", raw)}]
    if suffix in (".png", ".jpg", ".jpeg", ".tif", ".tiff"):
        return [{"page": 1, "text": _ocr_png(p.read_bytes())}]
    return [{"page": 1, "text": p.read_text(errors="ignore")}]


def _ocr_png(data: bytes) -> str:
    try:
        import io

        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(io.BytesIO(data)))
    except Exception:  # OCR is optional: tesseract binary may be missing
        return ""


def chunk_document(pages: list[dict], meta: dict, max_chars: int = 1100, overlap: int = 150) -> list[dict]:
    blocks, section, heading = [], "", meta.get("title", "")
    for pg in pages:
        buf: list[str] = []
        for line in pg["text"].splitlines():
            m = HEADING.match(line) if len(line) < 160 else None
            if m and (m.group("md") or m.group("num")):
                if "".join(buf).strip():
                    blocks.append({"page": pg["page"], "section": section, "heading": heading, "text": "\n".join(buf).strip()})
                buf = []
                section = m.group("num") or section
                heading = (m.group("md") or m.group("title") or "").strip()
            buf.append(line)
        if "".join(buf).strip():
            blocks.append({"page": pg["page"], "section": section, "heading": heading, "text": "\n".join(buf).strip()})
    chunks = []
    for b in blocks:
        text, start = b["text"], 0
        while start < len(text):
            end = min(len(text), start + max_chars)
            if end < len(text):  # prefer a paragraph or sentence boundary
                cut = max(text.rfind("\n", start, end), text.rfind(". ", start, end))
                end = cut + 1 if cut > start + max_chars // 2 else end
            body = text[start:end].strip()
            if body:
                chunks.append({**b, "text": f"{meta.get('title', '')} | {b['heading']}\n{body}".strip()})
            start = end if end >= len(text) else max(end - overlap, start + 1)
    for i, c in enumerate(chunks):
        c["chunk_id"] = f"{meta['doc_id']}::{i:04d}"
        c.update(_chunk_meta(meta))
    return chunks


def _chunk_meta(meta: dict) -> dict:
    """Chroma metadata must be scalars: dates as int YYYYMMDD (numeric filters), scopes as flags."""
    def day(v, default):
        return int(str(v)[:10].replace("-", "")) if v else default
    out = {"doc_id": meta["doc_id"], "title": meta.get("title", ""), "version": str(meta.get("version", "")),
           "authority_level": int(meta.get("authority_level", 4)), "doc_type": meta.get("doc_type", ""),
           "issuer": meta.get("issuer", ""), "effective_from": str(meta.get("effective_from", "")),
           "effective_to": str(meta.get("effective_to") or ""),
           "effective_from_i": day(meta.get("effective_from"), 0),
           "effective_to_i": day(meta.get("effective_to"), 99991231),
           "scope_categories": meta.get("scope_categories") or "ALL", "scope_tiers": meta.get("scope_tiers") or "ALL",
           "synthetic": str(meta.get("synthetic", "N"))}
    for kind in ("categories", "tiers"):
        for v in str(out[f"scope_{kind}"]).split(";"):
            out[f"{kind[:3]}_{v.strip().upper()}"] = True
    return out


def normalise_meta(meta: dict, path: str | Path) -> dict:
    m = {k: v for k, v in (meta or {}).items() if v not in (None, "")}
    m.setdefault("doc_id", Path(path).stem.upper())
    m.setdefault("title", Path(path).stem.replace("_", " "))
    m["authority_level"] = int(m.get("authority_level", 4))
    m.setdefault("effective_from", date.today().isoformat())
    for key in ("supersedes", "scope_categories", "scope_tiers"):
        if isinstance(m.get(key), (list, tuple)):
            m[key] = ";".join(m[key])
    return m


def ingest_document(path: str | Path, meta: dict, rules: list[dict] | None = None) -> dict:
    meta = normalise_meta(meta, path)
    sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    conn = connect()
    row = conn.execute("SELECT sha256 FROM source_register WHERE doc_id = ?", (meta["doc_id"],)).fetchone()
    if row and row[0] == sha and not rules:
        return {"doc_id": meta["doc_id"], "chunks_indexed": 0, "status": "unchanged"}
    pages = read_document(path)
    full_text = "\n".join(p["text"] for p in pages)
    chunks = chunk_document(pages, meta)
    index = get_index()
    index.delete_doc(meta["doc_id"])
    n = index.upsert_chunks(chunks)
    upsert_source(conn, meta, sha)
    rejected: list[dict] = []
    if rules:
        ids = upsert_rules(conn, rules, meta, origin="ingest-metadata")
    else:
        known = dict(conn.execute("SELECT parameter, MAX(description) FROM rule_registry GROUP BY parameter").fetchall())
        ok, rejected = extract_rules(meta, full_text, known)
        ids = upsert_rules(conn, ok, meta, origin="llm-verified")
    conn.commit()
    status = "updated" if row else "indexed"
    if not full_text.strip():
        status = "indexed_empty_text"   # scanned PDF without OCR: say so in the response
    version = log_ingest(conn, "document", meta["doc_id"], Path(path).name, sha, n, 0, status,
                         note=f"rules={ids}")
    return {"doc_id": meta["doc_id"], "chunks_indexed": n, "status": status, "rules_upserted": ids,
            "rules_rejected": rejected, "data_version": version}
