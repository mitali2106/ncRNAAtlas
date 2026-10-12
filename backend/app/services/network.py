"""Interaction-network generation from stored, source-supported relationships only.

Edges
-----
* ncRNA–disease: one edge per association in the database.
* ncRNA–gene: one edge per stored ncRNA–gene relationship (e.g. validated
  miRNA target), aggregated over sources/PMIDs.
* gene–disease: only where a source record links the gene to that specific
  ncRNA–disease association (``association_genes``). Genes are never
  connected to diseases merely because both are connected to an ncRNA.
"""
from collections import defaultdict

from sqlalchemy import func, select

from ..extensions import db
from ..models import (
    Association,
    AssociationGene,
    AssociationPublication,
    Disease,
    Gene,
    NcRNA,
    NcRNAGeneInteraction,
)
from ..models.constants import HUMAN

EDGE_KINDS = ("ncrna_disease", "ncrna_gene", "gene_disease")
MAX_EDGES = 600
DEFAULT_EDGES = 150
MAX_GENES_PER_NCRNA = 25


def build_network(focus_type=None, focus_id=None, ncrna_types=None, evidence_levels=None, include=EDGE_KINDS,
                  max_associations=DEFAULT_EDGES, organism=HUMAN):
    pub_count = (select(func.count(AssociationPublication.id))
                 .where(AssociationPublication.association_id == Association.id)
                 .correlate(Association).scalar_subquery())
    stmt = (select(Association, pub_count.label("pubs"))
            .join(NcRNA, Association.ncrna_id == NcRNA.id).join(Disease, Association.disease_id == Disease.id))
    if organism and organism != "all":
        stmt = stmt.where(NcRNA.organism == organism)
    if ncrna_types:
        stmt = stmt.where(NcRNA.ncrna_type.in_(ncrna_types))
    if evidence_levels:
        stmt = stmt.where(Association.evidence_level.in_(evidence_levels))
    focus_gene_ncrnas = None
    if focus_type == "ncrna":
        stmt = stmt.where(Association.ncrna_id == focus_id)
    elif focus_type == "disease":
        stmt = stmt.where(Association.disease_id == focus_id)
    elif focus_type == "gene":
        focus_gene_ncrnas = set(db.session.execute(
            select(NcRNAGeneInteraction.ncrna_id).where(NcRNAGeneInteraction.gene_id == focus_id)).scalars())
        linked = select(AssociationGene.association_id).where(AssociationGene.gene_id == focus_id)
        stmt = stmt.where((Association.ncrna_id.in_(focus_gene_ncrnas or {-1})) | Association.id.in_(linked))

    total = db.session.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = db.session.execute(stmt.order_by(pub_count.desc(), Association.id).limit(max_associations)).all()

    nodes, edges = {}, []

    def add_node(kind, entity_id, label, **data):
        node_id = f"{kind}-{entity_id}"
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "kind": kind, "entity_id": entity_id, "label": label, **data}
        return node_id

    assoc_ids, ncrna_ids = [], set()
    if "ncrna_disease" in include or "gene_disease" in include:
        for assoc, pubs in rows:
            n, d = assoc.ncrna, assoc.disease
            src = add_node("ncrna", n.id, n.canonical_name, ncrna_type=n.ncrna_type)
            dst = add_node("disease", d.id, d.canonical_name)
            ncrna_ids.add(n.id)
            assoc_ids.append(assoc.id)
            if "ncrna_disease" in include:
                edges.append({
                    "id": f"assoc-{assoc.id}", "source": src, "target": dst, "kind": "ncrna_disease",
                    "association_id": assoc.id, "association_type": assoc.association_type,
                    "evidence_level": assoc.evidence_level, "validation_status": assoc.validation_status,
                    "regulation_direction": assoc.regulation_direction, "publication_count": pubs,
                    "source_databases": sorted({s.source_database for s in assoc.sources}),
                })
    if focus_type == "gene":
        gene = db.session.get(Gene, focus_id)
        if gene is not None:
            add_node("gene", gene.id, gene.approved_gene_symbol)
        if focus_gene_ncrnas:
            for n in db.session.execute(select(NcRNA).where(NcRNA.id.in_(focus_gene_ncrnas))).scalars():
                if ncrna_types and n.ncrna_type not in ncrna_types:
                    continue
                add_node("ncrna", n.id, n.canonical_name, ncrna_type=n.ncrna_type)
                ncrna_ids.add(n.id)

    if "ncrna_gene" in include and ncrna_ids:
        inter_rows = db.session.execute(
            select(NcRNAGeneInteraction).where(NcRNAGeneInteraction.ncrna_id.in_(ncrna_ids))
            .order_by(NcRNAGeneInteraction.ncrna_id, NcRNAGeneInteraction.evidence_strength,
                      NcRNAGeneInteraction.id)
        ).scalars().all()
        grouped = defaultdict(list)
        for i in inter_rows:
            grouped[(i.ncrna_id, i.gene_id, i.relationship)].append(i)
        per_ncrna = defaultdict(int)
        for (nid, gid, rel), items in grouped.items():
            if focus_type != "gene" or gid != focus_id:
                if per_ncrna[nid] >= MAX_GENES_PER_NCRNA:
                    continue
                per_ncrna[nid] += 1
            g = items[0].gene
            add_node("gene", g.id, g.approved_gene_symbol)
            edges.append({
                "id": f"int-{nid}-{gid}-{rel}", "source": f"ncrna-{nid}", "target": f"gene-{gid}",
                "kind": "ncrna_gene", "relationship": rel,
                "evidence_strength": sorted({i.evidence_strength for i in items}),
                "source_databases": sorted({i.source_database for i in items}),
                "pmids": sorted({i.pmid for i in items if i.pmid}),
                "experimental_methods": sorted({i.experimental_methods for i in items if i.experimental_methods}),
            })

    if "gene_disease" in include and assoc_ids:
        links = db.session.execute(
            select(AssociationGene).where(AssociationGene.association_id.in_(assoc_ids))
        ).scalars().all()
        for link in links:
            g, d = link.gene, link.association.disease
            add_node("gene", g.id, g.approved_gene_symbol)
            add_node("disease", d.id, d.canonical_name)
            edges.append({
                "id": f"ag-{link.id}", "source": f"gene-{g.id}", "target": f"disease-{d.id}",
                "kind": "gene_disease", "relationship": link.gene_relationship,
                "association_id": link.association_id, "source_databases": [link.source_database],
                "pmids": [link.pmid] if link.pmid else [], "evidence_description": link.evidence_description,
            })

    degree = defaultdict(int)
    for e in edges:
        degree[e["source"]] += 1
        degree[e["target"]] += 1
    for node_id, node in nodes.items():
        node["degree"] = degree[node_id]
    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "meta": {
            "associations_matching": total,
            "associations_shown": len(rows),
            "truncated": total > len(rows),
            "max_associations": max_associations,
            "max_genes_per_ncrna": MAX_GENES_PER_NCRNA,
            "edge_policy": "Edges are drawn only for relationships stored in the database with source provenance.",
        },
    }
