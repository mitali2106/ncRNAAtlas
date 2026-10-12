"""Database models: creation, relationships, foreign keys and uniqueness constraints."""
import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    Association,
    AssociationPublication,
    AssociationSource,
    Disease,
    Gene,
    GenePathway,
    NcRNA,
    Pathway,
    Publication,
)


def make_core():
    n = NcRNA(canonical_name="hsa-mir-21", ncrna_type="miRNA", organism="Homo sapiens", source_database="test")
    d = Disease(canonical_name="Breast Neoplasms", normalized_name="breast neoplasms")
    db.session.add_all([n, d])
    db.session.flush()
    a = Association(ncrna_id=n.id, disease_id=d.id, association_type="expression")
    db.session.add(a)
    db.session.flush()
    return n, d, a


def test_entity_creation_and_defaults(app):
    n, d, a = make_core()
    db.session.commit()
    assert n.id and d.id and a.id
    assert a.evidence_level == "unverified"
    assert a.validation_status == "not_reviewed"
    assert a.confidence_score is None
    assert n.created_at is not None and n.is_synthetic is False


def test_ncrna_unique_per_organism(app):
    make_core()
    db.session.add(NcRNA(canonical_name="hsa-mir-21", ncrna_type="miRNA", organism="Mus musculus",
                         source_database="test"))
    db.session.commit()  # same name, different organism is allowed
    db.session.add(NcRNA(canonical_name="hsa-mir-21", ncrna_type="miRNA", organism="Homo sapiens",
                         source_database="test"))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_ncrna_type_check_constraint(app):
    db.session.add(NcRNA(canonical_name="circX", ncrna_type="circRNA", source_database="test"))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_association_identity_is_unique(app):
    n, d, _ = make_core()
    db.session.add(Association(ncrna_id=n.id, disease_id=d.id, association_type="expression"))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_foreign_keys_are_enforced(app):
    db.session.add(Association(ncrna_id=999, disease_id=999, association_type="expression"))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_association_publication_relationship_and_uniqueness(app):
    _, _, a = make_core()
    p = Publication(pmid="17681183", publication_url="https://pubmed.ncbi.nlm.nih.gov/17681183/")
    db.session.add(p)
    db.session.flush()
    db.session.add(AssociationPublication(association_id=a.id, publication_id=p.id, source_databases="HMDD"))
    db.session.commit()
    assert a.publication_links[0].publication.pmid == "17681183"
    assert p.association_links[0].association is a
    db.session.add(AssociationPublication(association_id=a.id, publication_id=p.id, source_databases="X"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    db.session.add(Publication(pmid="17681183", publication_url="x"))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_association_sources_unique_per_record(app):
    _, _, a = make_core()
    db.session.add(AssociationSource(association_id=a.id, source_database="HMDD", source_record_id="r1"))
    db.session.add(AssociationSource(association_id=a.id, source_database="LncRNADisease", source_record_id="r1"))
    db.session.commit()
    assert len(a.sources) == 2
    db.session.add(AssociationSource(association_id=a.id, source_database="HMDD", source_record_id="r1"))
    with pytest.raises(IntegrityError):
        db.session.commit()


@pytest.mark.filterwarnings("ignore:New instance .* conflicts with persistent instance")
def test_gene_pathway_relationship(app):
    g = Gene(approved_gene_symbol="PTEN", stable_gene_identifier="5728", identifier_namespace="NCBIGene")
    p = Pathway(pathway_identifier="hsa04151", pathway_name="PI3K-Akt signaling pathway")
    db.session.add_all([g, p])
    db.session.flush()
    db.session.add(GenePathway(gene_id=g.id, pathway_id=p.id))
    db.session.commit()
    assert g.pathway_links[0].pathway.pathway_identifier == "hsa04151"
    assert p.gene_links[0].gene.approved_gene_symbol == "PTEN"
    assert p.gene_links[0].mapping_type == "direct"
    db.session.add(GenePathway(gene_id=g.id, pathway_id=p.id))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_deleting_ncrna_cascades_to_associations_and_provenance(app):
    n, _, a = make_core()
    db.session.add(AssociationSource(association_id=a.id, source_database="HMDD", source_record_id="r1"))
    db.session.commit()
    db.session.delete(n)
    db.session.commit()
    assert db.session.query(Association).count() == 0
    assert db.session.query(AssociationSource).count() == 0
