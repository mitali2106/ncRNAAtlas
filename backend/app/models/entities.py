"""Core biological entities: ncRNAs, diseases, genes and their aliases."""
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from ..extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class NcRNA(TimestampMixin, db.Model):
    __tablename__ = "ncrnas"
    __table_args__ = (
        UniqueConstraint("canonical_name", "organism"),
        CheckConstraint("ncrna_type IN ('miRNA', 'lncRNA')", name="ncrna_type_valid"),
        Index("ix_ncrnas_type_organism", "ncrna_type", "organism"),
    )

    id = db.Column(db.Integer, primary_key=True)
    canonical_name = db.Column(db.String(128), nullable=False, index=True)
    # miRBase precursor accession (miRNA) or HGNC ID (lncRNA) when resolvable.
    stable_identifier = db.Column(db.String(64), nullable=True, index=True)
    identifier_namespace = db.Column(db.String(32), nullable=True)
    ncrna_type = db.Column(db.String(16), nullable=False)
    organism = db.Column(db.String(64), nullable=False, default="Homo sapiens")
    sequence = db.Column(db.Text, nullable=True)
    sequence_source = db.Column(db.String(64), nullable=True)
    description = db.Column(db.Text, nullable=True)
    source_database = db.Column(db.String(64), nullable=False)
    source_url = db.Column(db.String(512), nullable=True)
    resolution_status = db.Column(db.String(16), nullable=False, default="unresolved")
    resolution_note = db.Column(db.Text, nullable=True)
    is_synthetic = db.Column(db.Boolean, nullable=False, default=False)

    associations = db.relationship("Association", back_populates="ncrna", cascade="all, delete-orphan")
    gene_interactions = db.relationship("NcRNAGeneInteraction", back_populates="ncrna", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<NcRNA {self.canonical_name} ({self.ncrna_type})>"


class Disease(TimestampMixin, db.Model):
    __tablename__ = "diseases"
    __table_args__ = (Index("ix_diseases_identifier", "identifier_namespace", "disease_identifier"),)

    id = db.Column(db.Integer, primary_key=True)
    canonical_name = db.Column(db.String(255), nullable=False)
    normalized_name = db.Column(db.String(255), nullable=False, unique=True, index=True)
    disease_identifier = db.Column(db.String(64), nullable=True)
    identifier_namespace = db.Column(db.String(32), nullable=True)
    description = db.Column(db.Text, nullable=True)
    resolution_status = db.Column(db.String(16), nullable=False, default="unresolved")
    is_synthetic = db.Column(db.Boolean, nullable=False, default=False)

    associations = db.relationship("Association", back_populates="disease")

    def __repr__(self):
        return f"<Disease {self.canonical_name}>"


class Gene(TimestampMixin, db.Model):
    __tablename__ = "genes"
    __table_args__ = (UniqueConstraint("approved_gene_symbol", "organism"),)

    id = db.Column(db.Integer, primary_key=True)
    approved_gene_symbol = db.Column(db.String(64), nullable=False, index=True)
    # NCBI Gene (Entrez) ID: used for KEGG mapping (hsa:<id>).
    stable_gene_identifier = db.Column(db.String(32), nullable=True, index=True)
    identifier_namespace = db.Column(db.String(32), nullable=True)
    hgnc_id = db.Column(db.String(16), nullable=True)
    organism = db.Column(db.String(64), nullable=False, default="Homo sapiens")
    full_name = db.Column(db.String(255), nullable=True)
    locus_type = db.Column(db.String(64), nullable=True)
    resolution_status = db.Column(db.String(16), nullable=False, default="unresolved")
    is_synthetic = db.Column(db.Boolean, nullable=False, default=False)

    pathway_links = db.relationship("GenePathway", back_populates="gene", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Gene {self.approved_gene_symbol}>"


class Alias(db.Model):
    """Alternative names and external identifiers for any entity.

    ``entity_type`` is one of ``ncrna``, ``disease`` or ``gene``. Original
    names received from source databases are always preserved here so that a
    normalized entity can be traced back to the exact source spelling.
    """

    __tablename__ = "aliases"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "alias", "source_database"),
        Index("ix_aliases_lookup", "entity_type", "alias_normalized"),
        CheckConstraint("entity_type IN ('ncrna', 'disease', 'gene')", name="entity_type_valid"),
    )

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(16), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    alias = db.Column(db.String(255), nullable=False)
    alias_normalized = db.Column(db.String(255), nullable=False)
    # synonym | previous_symbol | source_name | identifier | mature_product
    alias_type = db.Column(db.String(32), nullable=False, default="synonym")
    namespace = db.Column(db.String(32), nullable=True)
    source_database = db.Column(db.String(64), nullable=False)
