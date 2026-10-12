"""Name cleaning, miRNA parsing and entity resolution (alias, gene and disease normalization)."""
import pytest

from app.normalization.mirna import parse_mirna
from app.normalization.resolver import EntityResolver
from app.normalization.text import clean_pmid, clean_text, like_escape, normalize_key, split_pmids
from app.services.hgnc import HGNCIndex
from conftest import FIXTURES


@pytest.fixture(scope="module")
def resolver():
    import json

    mesh = json.loads((FIXTURES / "mesh_cache.json").read_text())
    return EntityResolver(HGNCIndex.from_file(FIXTURES / "hgnc_small.tsv"), mesh_cache=mesh)


def test_clean_text_trims_and_preserves_case():
    assert clean_text('  "hsa-miR-21-5p"  ') == "hsa-miR-21-5p"
    assert clean_text("Breast   Neoplasms\t") == "Breast Neoplasms"
    assert clean_text("") is None and clean_text(None) is None and clean_text(float("nan")) is None


def test_normalize_key_is_case_and_spacing_insensitive():
    assert normalize_key("Carcinoma ,  Hepatocellular") == normalize_key("carcinoma, hepatocellular")
    assert normalize_key("Leukemia, Lymphocytic, Chronic, B - Cell") == "leukemia, lymphocytic, chronic, b-cell"


def test_pmid_cleaning_rejects_malformed_values():
    assert clean_pmid("17681183") == "17681183"
    assert clean_pmid("17681183.0") == "17681183"
    assert clean_pmid("PMID:123") is None
    assert clean_pmid("0") is None
    assert split_pmids("17681183; 16166262,17681183 | x") == ["17681183", "16166262"]


def test_like_escape():
    assert like_escape("50%_a\\") == "50\\%\\_a\\\\"


@pytest.mark.parametrize("name,precursor,symbol,mature", [
    ("hsa-mir-21", "hsa-mir-21", "MIR21", False),
    ("hsa-miR-21-5p", "hsa-mir-21", "MIR21", True),
    ("hsa-mir-125b-1", "hsa-mir-125b-1", "MIR125B1", False),
    ("hsa-mir-1-1", "hsa-mir-1-1", "MIR1-1", False),
    ("hsa-let-7a-1", "hsa-let-7a-1", "MIRLET7A1", False),
    ("miR-155", "hsa-mir-155", "MIR155", True),
])
def test_parse_mirna(name, precursor, symbol, mature):
    p = parse_mirna(name)
    assert p.precursor_name == precursor
    assert p.hgnc_symbol == symbol
    assert p.is_mature is mature


def test_parse_mirna_rejects_non_mirna():
    assert parse_mirna("MALAT1") is None
    assert parse_mirna("hsa-mir-17-92-cluster") is None


def test_mirna_resolves_to_mirbase_accession(resolver):
    r = resolver.resolve_ncrna("hsa-mir-21", "miRNA")
    assert r.status == "resolved"
    assert r.canonical_name == "hsa-mir-21"
    assert (r.stable_identifier, r.identifier_namespace) == ("MI0000077", "miRBase")
    assert ("MIR21", "synonym", "HGNC") in r.aliases


def test_mature_name_resolves_to_precursor_and_is_kept_as_alias(resolver):
    r = resolver.resolve_ncrna("hsa-miR-21-5p", "miRNA")
    assert r.canonical_name == "hsa-mir-21" and r.status == "resolved"
    assert ("hsa-miR-21-5p", "mature_product", None) in r.aliases


def test_locus_ambiguous_mirna_is_flagged_not_merged(resolver):
    r = resolver.resolve_ncrna("hsa-mir-16", "miRNA")
    assert r.status == "ambiguous"
    assert r.canonical_name == "hsa-mir-16"
    assert set(r.extra["candidates"]) == {"MIR16-1", "MIR16-2"}
    assert r.stable_identifier is None


def test_digit_final_stem_only_matches_hyphenated_loci(resolver):
    # hsa-mir-1 must list MIR1-1/MIR1-2 only, never MIR100 or MIR122.
    r = resolver.resolve_ncrna("hsa-mir-1", "miRNA")
    assert r.status == "ambiguous" and set(r.extra["candidates"]) == {"MIR1-1", "MIR1-2"}
    assert set(resolver.resolve_ncrna("hsa-mir-125b", "miRNA").extra["candidates"]) == {"MIR125B1", "MIR125B2"}


def test_legacy_mirbase_name_resolves_via_hgnc_alias(resolver):
    r = resolver.resolve_ncrna("hsa-mir-122a", "miRNA")  # retired name of hsa-mir-122
    assert r.status == "resolved" and r.canonical_name == "hsa-mir-122"
    assert r.stable_identifier == "MI0000442" and "Legacy name" in r.note
    assert any(a[0] == "hsa-mir-122a" for a in r.aliases)
    current = resolver.resolve_ncrna("hsa-mir-122", "miRNA")
    assert current.canonical_name == "hsa-mir-122" and current.note is None
    renamed = resolver.resolve_ncrna("hsa-mir-208", "miRNA")  # renamed hsa-mir-208a
    assert renamed.canonical_name == "hsa-mir-208a" and renamed.status == "resolved"


def test_hgnc_symbol_to_mirbase_name():
    from app.normalization.resolver import hgnc_symbol_to_mirbase_name as f

    assert [f(s) for s in ("MIR21", "MIR125B1", "MIR1-1", "MIRLET7A1", "MIR103A2", "MIR124-2")] == [
        "hsa-mir-21", "hsa-mir-125b-1", "hsa-mir-1-1", "hsa-let-7a-1", "hsa-mir-103a-2", "hsa-mir-124-2"]
    assert f("MIR1-1HG") is None  # host gene, not a miRNA locus


def test_lncrna_previous_symbol_resolves_to_approved_symbol(resolver):
    r = resolver.resolve_ncrna("LINC00152", "lncRNA")
    assert r.status == "resolved"
    assert r.canonical_name == "CYTOR"
    assert r.stable_identifier.startswith("HGNC:")
    assert any(a[0] == "LINC00152" and a[1] == "previous_symbol" for a in r.aliases)


def test_lncrna_name_matching_protein_coding_gene_is_not_merged(resolver):
    r = resolver.resolve_ncrna("PTEN", "lncRNA")
    assert r.status == "unresolved"
    assert "protein-coding" in r.note


def test_gene_alias_resolution(resolver):
    r = resolver.resolve_gene("MMAC1")
    assert r.status == "resolved" and r.canonical_name == "PTEN"
    assert (r.stable_identifier, r.identifier_namespace) == ("5728", "NCBIGene")


def test_gene_resolution_by_entrez_id(resolver):
    r = resolver.resolve_gene("bcl-2", entrez_id="596")
    assert r.canonical_name == "BCL2" and r.status == "resolved"


def test_unknown_gene_is_unresolved(resolver):
    assert resolver.resolve_gene("NOTAGENE1").status == "unresolved"


def test_disease_exact_mesh_match_only(resolver):
    hit = resolver.resolve_disease("carcinoma,  hepatocellular")
    assert hit.status == "resolved" and hit.stable_identifier == "D006528"
    assert hit.canonical_name == "Carcinoma, Hepatocellular"
    term = resolver.resolve_disease("Hepatocellular carcinoma")  # MeSH entry term of D006528
    assert term.status == "resolved" and term.stable_identifier == "D006528"
    assert term.canonical_name == "Carcinoma, Hepatocellular" and "entry term" in term.note
    assert ("Hepatocellular carcinoma", "source_name", None) in term.aliases
    miss = resolver.resolve_disease("Liver cancer of hepatocytes")  # neither a descriptor nor an entry term
    assert miss.status == "unresolved" and miss.stable_identifier is None


def test_non_human_entities_are_not_resolved_against_hgnc(resolver):
    r = resolver.resolve_ncrna("Malat1", "lncRNA", organism="Mus musculus")
    assert r.status == "not_attempted" and r.canonical_name == "Malat1"
    assert resolver.resolve_gene("Pten", organism="Mus musculus").status == "not_attempted"


def test_hgnc_ambiguous_alias_is_not_resolved():
    from app.services.hgnc import HGNCRecord

    idx = HGNCIndex([
        HGNCRecord("HGNC:1", "AAA1", "a", "protein-coding gene", "gene", alias_symbols=["SHARED"]),
        HGNCRecord("HGNC:2", "BBB1", "b", "protein-coding gene", "gene", alias_symbols=["SHARED"]),
    ])
    rec, method, cands = idx.lookup("shared")
    assert rec is None and method == "ambiguous_alias_symbol" and len(cands) == 2
