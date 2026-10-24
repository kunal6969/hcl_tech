# file: app/tools/search.py
"""search_documents: retrieval with effective-date, scope, authority and supersession handling + sufficiency."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.data.db import connect
from app.rag.index import get_index
from app.tools.common import as_date
from app.tools.registry import ToolContext, ToolSpec, register

SYNONYMS = {  # fill at S2 from the documents' own vocabulary; paraphrases are a stated trap
    "send back": "return", "money back": "refund", "broken": "defective",
}
MIN_OVERLAP = 0.34   # share of content words found in the best chunk; tune with the eval (A/B)


class SearchIn(BaseModel):
    query: str = Field(description="the user's question or a focused rewrite of it")
    category: str | None = Field(None, description="product/asset category if known")
    tier: str | None = None


def _superseded_refs(as_of: date) -> set[str]:
    rows = connect().execute("SELECT supersedes, effective_from, effective_to, authority_level FROM source_register "
                             "WHERE COALESCE(supersedes, '') != ''").fetchall()
    out: set[str] = set()
    for sup, start, end, level in rows:
        if int(level) <= 2 and as_date(start) <= as_of and (not end or as_date(end) >= as_of):
            out |= {s.strip().upper() for s in sup.split(";") if s.strip()}
    return out


def _in_scope(hit: dict, category: str | None, tier: str | None) -> bool:
    ok_cat = category is None or hit.get("cat_ALL") or hit.get(f"cat_{category.upper()}")
    ok_tier = tier is None or hit.get("tie_ALL") or hit.get(f"tie_{tier.upper()}")
    return bool(ok_cat and ok_tier)


def search_documents(args: SearchIn, ctx: ToolContext) -> dict:
    as_of = as_date(ctx.as_of, date.today())
    as_of_i = int(as_of.strftime("%Y%m%d"))
    query = args.query + "".join(f" {v}" for k, v in SYNONYMS.items() if k in args.query.lower())
    k = int(ctx.config.get("top_k", 5))
    hits = [h for h in get_index().search(query, k=k) if _in_scope(h, args.category, args.tier)]
    superseded = _superseded_refs(as_of)
    applicable, upcoming, other = [], [], []
    for h in hits:
        ref = f"{h['doc_id']}#{h.get('section', '')}".upper()
        if h.get("effective_from_i", 0) > as_of_i:
            upcoming.append(h)
        elif h.get("effective_to_i", 99991231) < as_of_i or ref in superseded or h["doc_id"].upper() in superseded:
            other.append({**h, "status": "superseded_or_expired"})
        elif int(h.get("authority_level", 4)) >= 5:
            other.append({**h, "status": "informational_unofficial"})
        else:
            applicable.append(h)
    min_overlap = float(ctx.config.get("min_overlap", MIN_OVERLAP))
    applicable.sort(key=lambda h: (h["overlap"] < min_overlap, int(h.get("authority_level", 4)), -h["score"]))
    best = max((h["overlap"] for h in applicable), default=0.0)
    sufficient = best >= min_overlap
    keep = ("doc_id", "title", "section", "page", "version", "effective_from", "authority_level", "text", "score",
            "overlap", "chunk_id")
    return {"sufficient": sufficient, "best_overlap": best,
            "evidence": [{k: h.get(k) for k in keep} for h in applicable[:k]] if sufficient else [],
            "upcoming": [{k: h.get(k) for k in keep} for h in upcoming[:3]],
            "excluded": [{"doc_id": h["doc_id"], "section": h.get("section"), "status": h["status"]} for h in other[:5]]}


register(ToolSpec("search_documents", "find governing policy text with citations (date- and scope-aware)",
                  SearchIn, search_documents))
