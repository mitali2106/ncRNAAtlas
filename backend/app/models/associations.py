"""ncRNA–disease associations, their provenance, publications and genes."""
from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from ..extensions import db
from .entities import TimestampMixin, utcnow


class Association(TimestampMixin, db.Model):
    """One ncRNA–disease relationship of a given type.

    Identity (and therefore deduplication) is defined by the canonical ncRNA
    entity (which already encodes organism), the normalized disease entity
    and the association type. Every supporting source record and publication
    is kept in child tables, never discarded on merge.
    """

    __tablename__ = "associations"
    __table_args__ = (
        UniqueConstraint("ncrna_id", "disease_id", "association_type"),
        Index("ix_associations_evidence", "evidence_level", "validation_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    ncrna_id = db.Column(db.Integer, db.ForeignKey("ncrnas.id", ondelete="CASCADE"), nullable=False, index=True)
    disease_id = db.Column(db.Integer, db.ForeignKey("diseases.id", ondelete="CASCADE"), nullable=False, index=True)
    association_type = db.Column(db.String(32), nullable=False, index=True)
    regulation_direction = db.Column(db.String(16), nullable=True)
    experimental_evidence_summary = db.Column(db.Text, nullable=True)
    evidence_level = db.Column(db.String(32), nullable=False, default="unverified")
    validation_status = db.Column(db.String(32), nullable=False, default="not_reviewed")
    # Intentionally never populated automatically: no scoring methodology is
    # implemented, so no score is invented.
    confidence_score = db.Column(db.Float, nullable=True)
    first_reported_date = db.Column(db.Date, nullable=True)
    last_verified_at = db.Column(db.DateTime(timezone=True), nullable=True)
    is_synthetic = db.Column(db.Boolean, nullable=False, default=False)

    ncrna = db.relationship("NcRNA", back_populates="associations")
    disease = db.relationship("Disease", back_populates="associations")
    sources = db.relationship("AssociationSource", back_populates="association", cascade="all, delete-orphan")
    publication_links = db.relationship(
        "AssociationPublication", back_populates="association", cascade="all, delete-orphan"
    )
    gene_links = db.relationship("AssociationGene", back_populates="association", cascade="all, delete-orphan")
    reviews = db.relationship("LiteratureReview", back_populates="association", cascade="all, delete-orphan")


class AssociationSource(db.Model):
    """Provenance: one source record supporting an association."""

    __tablename__ = "association_sources"
    __table_args__ = (UniqueConstraint("association_id", "source_database", "source_record_id"),)

    id = db.Column(db.Integer, primary_key=True)
    association_id = db.Column(
        db.Integer, db.ForeignKey("associations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_database = db.Column(db.String(64), nullable=False, index=True)
    source_record_id = db.Column(db.String(128), nullable=False)
    source_url = db.Column(db.String(512), nullable=True)
    source_version = db.Column(db.String(64), nullable=True)
    import_timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    import_job_id = db.Column(db.Integer, db.ForeignKey("import_jobs.id", ondelete="SET NULL"), nullable=True)
    # Per-record evidence as classified from this source record alone.
    evidence_level = db.Column(db.String(32), nullable=False, default="unverified")
    regulation_direction = db.Column(db.String(16), nullable=True)
    source_category = db.Column(db.String(128), nullable=True)
    experimental_methods = db.Column(db.Text, nullable=True)
    evidence_text = db.Column(db.Text, nullable=True)
    pmid = db.Column(db.String(16), nullable=True)
    original_record = db.Column(db.JSON, nullable=True)

    association = db.relationship("Association", back_populates="sources")


class Publication(db.Model):
    """Bibliographic metadata, stored once per PMID."""

    __tablename__ = "publications"

    id = db.Column(db.Integer, primary_key=True)
    pmid = db.Column(db.String(16), nullable=False, unique=True, index=True)
    doi = db.Column(db.String(255), nullable=True, index=True)
    publication_title = db.Column(db.Text, nullable=True)
    authors = db.Column(db.Text, nullable=True)
    journal = db.Column(db.String(512), nullable=True)
    publication_year = db.Column(db.Integer, nullable=True, index=True)
    abstract = db.Column(db.Text, nullable=True)
    publication_url = db.Column(db.String(255), nullable=False)
    # pending | fetched | not_found | error
    metadata_status = db.Column(db.String(16), nullable=False, default="pending")
    fetched_at = db.Column(db.DateTime(timezone=True), nullable=True)

    association_links = db.relationship("AssociationPublication", back_populates="publication")


class AssociationPublication(db.Model):
    """Link between an association and a publication cited by a source."""

    __tablename__ = "association_publications"
    __table_args__ = (UniqueConstraint("association_id", "publication_id"),)

    id = db.Column(db.Integer, primary_key=True)
    association_id = db.Column(
        db.Integer, db.ForeignKey("associations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    publication_id = db.Column(
        db.Integer, db.ForeignKey("publications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # "; "-joined names of the source databases citing this PMID for this association.
    source_databases = db.Column(db.String(255), nullable=False)
    evidence_notes = db.Column(db.Text, nullable=True)

    association = db.relationship("Association", back_populates="publication_links")
    publication = db.relationship("Publication", back_populates="association_links")


class AssociationGene(db.Model):
    """A gene linked to one specific association by a source record."""

    __tablename__ = "association_genes"
    __table_args__ = (
        UniqueConstraint("association_id", "gene_id", "gene_relationship", "source_database"),
        CheckConstraint(
            "gene_relationship IN ('experimentally_validated_target', 'inferred_target', "
            "'disease_associated_gene', 'indirectly_related')",
            name="gene_relationship_valid",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    association_id = db.Column(
        db.Integer, db.ForeignKey("associations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    gene_id = db.Column(db.Integer, db.ForeignKey("genes.id", ondelete="CASCADE"), nullable=False, index=True)
    gene_relationship = db.Column(db.String(40), nullable=False)
    evidence_description = db.Column(db.Text, nullable=True)
    source_database = db.Column(db.String(64), nullable=False)
    pmid = db.Column(db.String(16), nullable=True)

    association = db.relationship("Association", back_populates="gene_links")
    gene = db.relationship("Gene")


class NcRNAGeneInteraction(db.Model):
    """ncRNA → gene relationship independent of any disease (e.g. miRNA targets).

    Kept separate from :class:`AssociationGene` so that a general target
    relationship is never presented as disease-specific evidence.
    """

    __tablename__ = "ncrna_gene_interactions"
    __table_args__ = (
        UniqueConstraint("ncrna_id", "gene_id", "relationship", "source_database", "pmid"),
        CheckConstraint(
            "relationship IN ('experimentally_validated_target', 'inferred_target', "
            "'disease_associated_gene', 'indirectly_related')",
            name="relationship_valid",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    ncrna_id = db.Column(db.Integer, db.ForeignKey("ncrnas.id", ondelete="CASCADE"), nullable=False, index=True)
    gene_id = db.Column(db.Integer, db.ForeignKey("genes.id", ondelete="CASCADE"), nullable=False, index=True)
    relationship = db.Column(db.String(40), nullable=False)
    evidence_strength = db.Column(db.String(16), nullable=False, default="not_stated")
    experimental_methods = db.Column(db.Text, nullable=True)
    evidence_description = db.Column(db.Text, nullable=True)
    source_database = db.Column(db.String(64), nullable=False)
    source_record_id = db.Column(db.String(128), nullable=True)
    pmid = db.Column(db.String(16), nullable=True)
    original_record = db.Column(db.JSON, nullable=True)
    import_timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    is_synthetic = db.Column(db.Boolean, nullable=False, default=False)

    ncrna = db.relationship("NcRNA", back_populates="gene_interactions")
    gene = db.relationship("Gene")


class LiteratureReview(db.Model):
    """One review of one publication for one association.

    ``review_type='automated_triage'`` rows hold machine-generated hints only
    (e.g. whether the abstract mentions both entities) and never change the
    association's validation status. Only ``curator`` reviews do.
    """

    __tablename__ = "literature_reviews"

    id = db.Column(db.Integer, primary_key=True)
    association_id = db.Column(
        db.Integer, db.ForeignKey("associations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pmid = db.Column(db.String(16), nullable=True)
    review_type = db.Column(db.String(24), nullable=False, default="curator")
    outcome = db.Column(db.String(40), nullable=True)
    evidence_type = db.Column(db.String(128), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    flags = db.Column(db.JSON, nullable=True)
    reviewer = db.Column(db.String(128), nullable=True)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    association = db.relationship("Association", back_populates="reviews")
