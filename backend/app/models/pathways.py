"""KEGG pathways and gene-to-pathway mappings."""
from sqlalchemy import UniqueConstraint

from ..extensions import db
from .entities import utcnow


class Pathway(db.Model):
    __tablename__ = "pathways"
    __table_args__ = (UniqueConstraint("pathway_database", "pathway_identifier"),)

    id = db.Column(db.Integer, primary_key=True)
    pathway_identifier = db.Column(db.String(32), nullable=False, index=True)
    pathway_name = db.Column(db.String(255), nullable=True)
    pathway_database = db.Column(db.String(32), nullable=False, default="KEGG")
    organism = db.Column(db.String(64), nullable=False, default="Homo sapiens")
    pathway_url = db.Column(db.String(512), nullable=True)
    description = db.Column(db.Text, nullable=True)

    gene_links = db.relationship("GenePathway", back_populates="pathway", cascade="all, delete-orphan")


class GenePathway(db.Model):
    """A gene-to-pathway membership as reported by the mapping source.

    ``mapping_type`` is always ``direct`` for rows in this table (the gene's
    own identifier was linked to the pathway by KEGG). Pathways shown for an
    ncRNA or disease are *inferred* at query time through associated genes
    and are labelled as such by the API.
    """

    __tablename__ = "gene_pathways"

    gene_id = db.Column(db.Integer, db.ForeignKey("genes.id", ondelete="CASCADE"), primary_key=True)
    pathway_id = db.Column(db.Integer, db.ForeignKey("pathways.id", ondelete="CASCADE"), primary_key=True)
    mapping_source = db.Column(db.String(64), nullable=False, default="KEGG REST API")
    mapping_type = db.Column(db.String(16), nullable=False, default="direct")
    source_gene_identifier = db.Column(db.String(32), nullable=True)
    mapping_timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    gene = db.relationship("Gene", back_populates="pathway_links")
    pathway = db.relationship("Pathway", back_populates="gene_links")
