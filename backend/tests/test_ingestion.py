"""Import pipeline: adapters, deduplication, provenance, organism handling and QC reports."""
import json

from sqlalchemy import func, select

from app.extensions import db
from app.ingestion.adapters import MiRTarBaseAdapter, Skip
from app.ingestion.runner import run_import
from app.models import (
    Alias,
    Association,
    AssociationPublication,
    AssociationSource,
    Disease,
    Gene,
    ImportJob,
    NcRNA,
    NcRNAGeneInteraction,
    Publication,
)
from app.services.mirbase import parse_mirna_dat
from conftest import FIXTURES, GENERIC_ASSOCIATIONS


def count(model):
    return db.session.execute(select(func.count()).select_from(model)).scalar()


def test_hmdd_import_deduplicates_and_keeps_provenance(app):
    result, job = run_import("hmdd", FIXTURES / "hmdd_small.tsv", source_version="test")
    assert not result.errors
    assert job.status == "completed" and job.records_processed == result.raw_records == 72
    n_assoc = count(Association)
    # Several HMDD categories collapse onto one association type, so records merge.
    assert 0 < n_assoc < result.valid_records
    assert result.merged_into_existing == result.valid_records - n_assoc
    # Every source record is preserved, and every association has provenance.
    assert count(AssociationSource) == result.valid_records
    orphan = select(Association.id).where(~select(AssociationSource.id).where(
        AssociationSource.association_id == Association.id).exists())
    assert db.session.execute(orphan).first() is None
    a = db.session.execute(select(Association).limit(1)).scalar_one()
    assert a.experimental_evidence_summary and "HMDD" in a.experimental_evidence_summary


def test_reimport_is_idempotent(app):
    first, _ = run_import("hmdd", FIXTURES / "hmdd_small.tsv")
    before = (count(Association), count(AssociationSource), count(Publication))
    second, job = run_import("hmdd", FIXTURES / "hmdd_small.tsv")
    assert second.inserted == 0 and second.updated == 0
    assert second.unchanged == first.valid_records
    assert (count(Association), count(AssociationSource), count(Publication)) == before
    assert db.session.execute(select(func.count(ImportJob.id))).scalar() == 2


def test_ambiguous_mirna_is_imported_but_flagged(app):
    run_import("hmdd", FIXTURES / "hmdd_small.tsv")
    mir16 = db.session.execute(select(NcRNA).filter_by(canonical_name="hsa-mir-16")).scalar_one()
    assert mir16.resolution_status == "ambiguous" and mir16.stable_identifier is None
    mir21 = db.session.execute(select(NcRNA).filter_by(canonical_name="hsa-mir-21")).scalar_one()
    assert mir21.resolution_status == "resolved" and mir21.stable_identifier == "MI0000077"


def test_lncrnadisease_skips_circrna_and_labels_non_human(app):
    result, _ = run_import("lncrnadisease", FIXTURES / "lncrnadisease_small.tsv")
    assert result.skip_reasons["unsupported_ncrna_class"] == 1
    assert result.non_human_records == 1
    mouse = db.session.execute(select(NcRNA).where(NcRNA.organism == "Mus musculus")).scalars().all()
    assert len(mouse) == 1 and mouse[0].resolution_status == "not_attempted"
    malat1 = db.session.execute(select(NcRNA).filter_by(canonical_name="MALAT1")).scalar_one()
    assert malat1.stable_identifier == "HGNC:29665"


def test_human_only_option_excludes_non_human(app):
    result, _ = run_import("lncrnadisease", FIXTURES / "lncrnadisease_small.tsv", human_only=True)
    assert result.skip_reasons["non_human"] == 1
    assert db.session.execute(select(NcRNA).where(NcRNA.organism != "Homo sapiens")).first() is None


def test_generic_upload_alias_resolution_warnings_and_conflicts(app, write_file):
    result, _ = run_import("generic_associations", write_file("a.tsv", GENERIC_ASSOCIATIONS))
    d = result.to_dict()
    assert result.duplicates_in_file == 1
    assert d["skip_reasons"]["unsupported_ncrna_class"] == 1
    assert any("Malformed PMID" in w["message"] for w in d["warnings"])
    assert any("downgraded" in w["message"] for w in d["warnings"])
    # LINC00152 resolves to the approved symbol and keeps the original name as an alias.
    cytor = db.session.execute(select(NcRNA).filter_by(canonical_name="CYTOR")).scalar_one()
    aliases = {a.alias for a in db.session.execute(select(Alias).filter_by(entity_type="ncrna",
                                                                           entity_id=cytor.id)).scalars()}
    assert "LINC00152" in aliases
    # Up- and down-regulation for the same pair and type is flagged as conflicting.
    a = db.session.execute(select(Association).filter_by(ncrna_id=cytor.id)).scalar_one()
    assert a.evidence_level == "conflicting" and a.regulation_direction == "mixed"
    assert len(a.publication_links) == 2
    # A name matching no MeSH descriptor or entry term stays unresolved (no fuzzy merge).
    unresolved = db.session.execute(select(Disease).filter_by(canonical_name="Liver cancer of hepatocytes")).scalar_one()
    assert unresolved.resolution_status == "unresolved"
    resolved = db.session.execute(select(Disease).filter_by(disease_identifier="D006528")).scalar_one()
    assert resolved.id != unresolved.id
    # Gene link stored with the declared relationship, normalized through HGNC.
    mir21 = db.session.execute(select(NcRNA).filter_by(canonical_name="hsa-mir-21")).scalar_one()
    link = db.session.execute(select(Association).filter_by(ncrna_id=mir21.id)).scalar_one().gene_links[0]
    assert link.gene.approved_gene_symbol == "PTEN" and link.gene_relationship == "experimentally_validated_target"


def test_merge_across_sources_keeps_all_publications(app, write_file):
    run_import("hmdd", FIXTURES / "hmdd_small.tsv")
    mir21 = db.session.execute(select(NcRNA).filter_by(canonical_name="hsa-mir-21")).scalar_one()
    hcc = db.session.execute(select(Disease).filter_by(disease_identifier="D006528")).scalar_one()
    a = db.session.execute(select(Association).filter_by(ncrna_id=mir21.id, disease_id=hcc.id,
                                                         association_type="target_mediated")).scalar_one()
    pubs_before = {l.publication.pmid for l in a.publication_links}
    run_import("generic_associations", write_file("a.tsv", GENERIC_ASSOCIATIONS))
    db.session.refresh(a)
    pubs_after = {l.publication.pmid for l in a.publication_links}
    assert pubs_before < pubs_after and "17681183" in pubs_after
    assert {s.source_database for s in a.sources} == {"HMDD", "Test curation"}


def test_targets_import_and_relationship_safeguards(app, write_file):
    from conftest import GENERIC_TARGETS

    result, _ = run_import("generic_targets", write_file("t.tsv", GENERIC_TARGETS))
    d = result.to_dict()
    assert d["skip_reasons"]["invalid_relationship"] == 1
    assert any("without PMID" in w["message"] for w in d["warnings"])
    rows = db.session.execute(select(NcRNAGeneInteraction)).scalars().all()
    assert {r.gene.approved_gene_symbol for r in rows} == {"PTEN", "BCL2"}  # MMAC1 alias -> PTEN
    no_pmid = next(r for r in rows if r.gene.approved_gene_symbol == "BCL2")
    assert no_pmid.relationship == "inferred_target"
    assert db.session.execute(select(func.count(Gene.id))).scalar() == 2


def test_dry_run_writes_nothing(app):
    result, job = run_import("hmdd", FIXTURES / "hmdd_small.tsv", dry_run=True)
    assert job is None and result.valid_records == 72 and len(result.preview) == 50
    assert count(Association) == 0 and count(NcRNA) == 0 and count(ImportJob) == 0


def test_missing_columns_fail_cleanly(app, write_file):
    result, job = run_import("generic_associations", write_file("bad.tsv", "ncrna_name\tdisease_name\nx\ty\n"))
    assert job.status == "failed" and "Missing required column" in job.error_summary
    assert count(Association) == 0


def test_quality_report_contents(app, write_file):
    from app.validation.quality import generate_quality_report

    run_import("hmdd", FIXTURES / "hmdd_small.tsv")
    _, job = run_import("generic_associations", write_file("a.tsv", GENERIC_ASSOCIATIONS))
    report = json.loads(open(job.report_path, encoding="utf-8").read())
    m = report["metrics"]
    for key in ("unique_ncrnas", "unique_diseases", "unique_genes", "associations", "duplicate_records_in_files",
                "unresolved_rna_names", "unresolved_disease_names", "unresolved_gene_identifiers",
                "associations_missing_publication_evidence", "associations_missing_source_provenance",
                "associations_with_conflicting_evidence", "raw_records_imported_all_jobs"):
        assert key in m
    assert m["associations_missing_source_provenance"] == 0
    assert m["associations_with_conflicting_evidence"] >= 1
    assert m["duplicate_records_in_files"] == 1
    assert "hsa-mir-16" in {r["name"] for r in report["lists"]["unresolved_rna_names"]}
    assert report["import"]["duplicates_in_file"] == 1
    assert (job.report_path.endswith(".json"))
    assert generate_quality_report()["metrics"]["associations"] == m["associations"]


def test_reresolve_merges_synonym_disease_and_keeps_provenance(app, write_file):
    """A disease first left unresolved is merged into the existing entity once it resolves to the same MeSH ID."""
    from app.ingestion.enrichment import reresolve_diseases
    from app.normalization.resolver import EntityResolver
    from app.services.hgnc import HGNCIndex

    run_import("hmdd", FIXTURES / "hmdd_small.tsv")
    rows = ("ncrna_name\tncrna_type\tdisease_name\tsource_database\tpmid\tassociation_type\texperimental_methods\n"
            "hsa-mir-21\tmiRNA\tLiver cell carcinoma\tTest\t17681183\ttarget_mediated\tqRT-PCR\n"
            "hsa-mir-155\tmiRNA\tLiver cell carcinoma\tTest\t20354188\tregulatory\tqRT-PCR\n")
    run_import("generic_associations", write_file("syn.tsv", rows))
    syn = db.session.execute(select(Disease).filter_by(canonical_name="Liver cell carcinoma")).scalar_one()
    assert syn.resolution_status == "unresolved"
    hcc = db.session.execute(select(Disease).filter_by(disease_identifier="D006528")).scalar_one()
    before_sources = count(AssociationSource)
    mir21 = db.session.execute(select(NcRNA).filter_by(canonical_name="hsa-mir-21")).scalar_one()
    twin = db.session.execute(select(Association).filter_by(ncrna_id=mir21.id, disease_id=hcc.id,
                                                            association_type="target_mediated")).scalar_one()
    twin_id, twin_sources = twin.id, len(twin.sources)

    # Simulate the MeSH lookup now resolving the name as an exact synonym of D006528.
    resolver = EntityResolver(HGNCIndex.from_file(FIXTURES / "hgnc_small.tsv"), retry_mesh_misses=True,
                              mesh_cache={"liver cell carcinoma": {"id": "D006528", "label": "Carcinoma, Hepatocellular",
                                                                   "matched_via": "entry_term"}})
    report = reresolve_diseases(resolver)
    assert report["merged_into_existing"] == 1
    assert db.session.get(Disease, syn.id) is None
    assert count(AssociationSource) == before_sources  # nothing lost
    merged = db.session.get(Association, twin_id)
    assert len(merged.sources) == twin_sources + 1
    assert "17681183" in {l.publication.pmid for l in merged.publication_links}
    names = {a.alias for a in db.session.execute(select(Alias).filter_by(entity_type="disease",
                                                                         entity_id=hcc.id)).scalars()}
    assert "Liver cell carcinoma" in names
    # The non-colliding association was simply re-pointed to the merged disease.
    mir155 = db.session.execute(select(NcRNA).filter_by(canonical_name="hsa-mir-155")).scalar_one()
    assert db.session.execute(select(Association).filter_by(ncrna_id=mir155.id, disease_id=hcc.id,
                                                            association_type="regulatory")).scalar_one()


def test_publications_created_once_per_pmid(app):
    run_import("hmdd", FIXTURES / "hmdd_small.tsv")
    pmids = db.session.execute(select(Publication.pmid)).scalars().all()
    assert len(pmids) == len(set(pmids))
    linked = db.session.execute(select(func.count(func.distinct(AssociationPublication.publication_id)))).scalar()
    assert linked == len(pmids)


def test_mirtarbase_adapter_transform():
    row = {"miRTarBase ID": "MIRT-TEST-1", "miRNA": "hsa-miR-21-5p", "Species (miRNA)": "Homo sapiens",
           "Target Gene": "PTEN", "Target Gene (Entrez ID)": "5728", "Species (Target Gene)": "Homo sapiens",
           "Experiments": "Luciferase reporter assay//Western blot", "Support Type": "Functional MTI",
           "References (PMID)": "17681183"}
    rec = MiRTarBaseAdapter().transform(row)
    assert rec.relationship == "experimentally_validated_target" and rec.evidence_strength == "strong"
    weak = MiRTarBaseAdapter().transform({**row, "Support Type": "Functional MTI (Weak)"})
    assert weak.evidence_strength == "weak"
    assert isinstance(MiRTarBaseAdapter().transform({**row, "miRNA": ""}), Skip)


MIRNA_DAT = """ID   hsa-mir-21        standard; RNA; HSA; 72 BP.
XX
AC   MI0000077;
XX
DE   Homo sapiens miR-21 stem-loop
XX
FH   Key             Location/Qualifiers
FH
FT   miRNA           8..29
FT                   /accession="MIMAT0000076"
FT                   /product="hsa-miR-21-5p"
FT   miRNA           46..66
FT                   /accession="MIMAT0004494"
FT                   /product="hsa-miR-21-3p"
XX
SQ   Sequence 72 BP; 13 A; 16 C; 18 G; 0 T; 25 other;
     ugucggguag cuuaucagac ugauguugac uguugaaucu cauggcaaca ccagucgaug        60
     ggcugucuga ca                                                            72
//
"""


def test_mirbase_dat_parser():
    (entry,) = list(parse_mirna_dat(MIRNA_DAT))
    assert entry["id"] == "hsa-mir-21" and entry["accession"] == "MI0000077"
    assert len(entry["sequence"]) == 72 and entry["sequence"].startswith("UGUCGGG")
    p5 = entry["products"][0]
    assert p5["name"] == "hsa-miR-21-5p" and p5["sequence"] == "UAGCUUAUCAGACUGAUGUUGA"


def test_apply_mirbase_file_adds_sequence_and_mature_aliases(app, tmp_path):
    from app.ingestion.enrichment import apply_mirbase_file

    run_import("hmdd", FIXTURES / "hmdd_small.tsv")
    path = tmp_path / "miRNA.dat"
    path.write_text(MIRNA_DAT)
    report = apply_mirbase_file(path)
    assert report["matched"] == 1 and report["sequences_set"] == 1
    mir21 = db.session.execute(select(NcRNA).filter_by(canonical_name="hsa-mir-21")).scalar_one()
    assert mir21.sequence_source == "miRBase" and len(mir21.sequence) == 72
    names = {a.alias for a in db.session.execute(select(Alias).filter_by(entity_type="ncrna",
                                                                         entity_id=mir21.id)).scalars()}
    assert {"hsa-miR-21-5p", "MIMAT0000076"} <= names
