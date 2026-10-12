"""Global search and autocomplete over the local database (never fabricated)."""
from flask import Blueprint

from ..api_utils import APIError, get_int, get_str, ok
from ..extensions import db
from ..models import Association
from ..schemas import serializers as ser
from ..services import queries

bp = Blueprint("search", __name__)
CATEGORIES = ("ncrnas", "diseases", "genes", "publications", "pathways")


def _query():
    q = get_str("q")
    if not q or len(q) < 2:
        raise APIError(400, "Query parameter 'q' must contain at least 2 characters")
    return q


@bp.get("/search")
def search():
    q = _query()
    limit = get_int("limit", 10, 1, 50)
    types = [t for t in (get_str("types") or ",".join(CATEGORIES)).split(",") if t]
    bad = [t for t in types if t not in CATEGORIES]
    if bad:
        raise APIError(400, f"Invalid types: {', '.join(bad)}")
    results = {}
    if "ncrnas" in types:
        items = db.session.execute(queries.search_ncrnas(q, limit, organism="all")).scalars().all()
        counts = queries.association_counts(Association.ncrna_id, [n.id for n in items])
        results["ncrnas"] = [{**ser.ncrna_summary(n), "association_count": counts[n.id]} for n in items]
    if "diseases" in types:
        items = db.session.execute(queries.search_diseases(q, limit)).scalars().all()
        counts = queries.association_counts(Association.disease_id, [d.id for d in items])
        results["diseases"] = [{**ser.disease_summary(d), "association_count": counts[d.id]} for d in items]
    if "genes" in types:
        results["genes"] = [ser.gene_summary(g) for g in db.session.execute(queries.search_genes(q, limit)).scalars()]
    if "publications" in types:
        results["publications"] = [
            {k: v for k, v in ser.publication(p).items() if k != "abstract"}
            for p in db.session.execute(queries.search_publications(q, limit)).scalars()
        ]
    if "pathways" in types:
        results["pathways"] = [ser.pathway(p) for p in db.session.execute(queries.search_pathways(q, limit)).scalars()]
    total = sum(len(v) for v in results.values())
    return ok(results, query=q, total=total)


@bp.get("/search/suggest")
def suggest():
    q = _query()
    limit = get_int("limit", 8, 1, 20)
    out = []
    for n in db.session.execute(queries.search_ncrnas(q, limit, organism="all")).scalars():
        out.append({"type": "ncrna", "id": n.id, "label": n.canonical_name,
                    "detail": f"{n.ncrna_type} · {n.organism}" + (f" · {n.stable_identifier}" if n.stable_identifier else "")})
    for d in db.session.execute(queries.search_diseases(q, limit)).scalars():
        out.append({"type": "disease", "id": d.id, "label": d.canonical_name,
                    "detail": f"Disease" + (f" · MeSH {d.disease_identifier}" if d.disease_identifier else "")})
    for g in db.session.execute(queries.search_genes(q, limit)).scalars():
        out.append({"type": "gene", "id": g.id, "label": g.approved_gene_symbol, "detail": g.full_name or "Gene"})
    if q.isdigit():
        for p in db.session.execute(queries.search_publications(q, 1)).scalars():
            out.append({"type": "publication", "id": p.pmid, "label": f"PMID {p.pmid}",
                        "detail": (p.publication_title or "")[:90]})
    ql = q.lower()
    out.sort(key=lambda s: (0 if s["label"].lower() == ql else 1 if s["label"].lower().startswith(ql) else 2,
                            len(s["label"])))
    return ok(out[:limit], query=q)
