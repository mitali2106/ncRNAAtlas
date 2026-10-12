"""Evidence classification and validation-status derivation."""
from types import SimpleNamespace

import pytest

from app.validation.evidence import (
    aggregate_evidence,
    classify_generic,
    classify_hmdd,
    classify_lncrnadisease,
)
from app.validation.literature_review import derive_validation_status


@pytest.mark.parametrize("category,atype,direction,level", [
    ("tissue_expression_up", "expression", "up", "experimental"),
    ("tissue_expression_ns", "expression", "not_significant", "experimental"),
    ("circulation_biomarker_diagnosis_down", "circulating_biomarker", "down", "experimental"),
    ("circulation_biomarker_diagnosis-down", "circulating_biomarker", "down", "experimental"),
    ("genetics_knock down_promote", "functional", "unspecified", "experimental"),
    ("genetics_GWAS", "genetic_variant", "unspecified", "experimental"),
    ("target gene", "target_mediated", "unspecified", "experimental"),
    ("lncRNA target", "regulatory", "unspecified", "experimental"),
    ("other", "other", "unspecified", "literature_unclear"),
])
def test_classify_hmdd(category, atype, direction, level):
    c = classify_hmdd(category, "12345")
    assert (c["association_type"], c["regulation_direction"], c["evidence_level"]) == (atype, direction, level)


def test_hmdd_without_pmid_is_unverified_and_unknown_category_rejected():
    assert classify_hmdd("tissue_expression_up", None)["evidence_level"] == "unverified"
    assert classify_hmdd("made_up_category", "1") is None


@pytest.mark.parametrize("pattern,atype,direction", [
    ("Expression[highly expressed]", "expression", "up"),
    ("Expression (lower expressed)", "expression", "down"),
    ("Interaction(miR-145)", "regulatory", "unspecified"),
    ("Mutation[rs123]", "genetic_variant", "unspecified"),
    ("Epigenetics( m6 A-modified)", "epigenetic", "unspecified"),
    ("", "other", "unspecified"),
])
def test_classify_lncrnadisease(pattern, atype, direction):
    c = classify_lncrnadisease(pattern, "qRT-PCR", "1")
    assert (c["association_type"], c["regulation_direction"], c["evidence_level"]) == (atype, direction, "experimental")


def test_lncrnadisease_without_method_is_not_experimental():
    assert classify_lncrnadisease("Expression[highly expressed]", "", "1")["evidence_level"] == "literature_unclear"


def test_generic_declared_experimental_without_support_is_downgraded():
    level, warning = classify_generic("experimental", "", None)
    assert level == "unverified" and "downgraded" in warning
    assert classify_generic("", "Western blot", "1") == ("experimental", None)
    assert classify_generic("", "", "1") == ("literature_unclear", None)
    level, warning = classify_generic("proven", "", "1")
    assert level == "literature_unclear" and "Unknown" in warning


def test_aggregate_detects_conflicting_direction():
    rows = [{"evidence_level": "experimental", "regulation_direction": "up"},
            {"evidence_level": "experimental", "regulation_direction": "down"}]
    assert aggregate_evidence(rows) == ("conflicting", "mixed")


def test_aggregate_prefers_experimental_and_keeps_direction():
    rows = [{"evidence_level": "literature_unclear", "regulation_direction": "unspecified"},
            {"evidence_level": "experimental", "regulation_direction": "up"},
            {"evidence_level": "experimental", "regulation_direction": "not_significant"}]
    assert aggregate_evidence(rows) == ("experimental", "up")
    assert aggregate_evidence([]) == ("unverified", None)


def review(kind, outcome=None):
    return SimpleNamespace(review_type=kind, outcome=outcome)


def test_validation_status_requires_curator_reviews():
    assert derive_validation_status([]) == "not_reviewed"
    # Automated triage alone never confirms anything.
    assert derive_validation_status([review("automated_triage")]) == "under_review"
    assert derive_validation_status([review("curator", "supports_direct_experimental")]) == "curator_confirmed"
    assert derive_validation_status([review("curator", "supports_direct_experimental"),
                                     review("curator", "does_not_support")]) == "conflicting"
    assert derive_validation_status([review("curator", "does_not_support")]) == "curator_rejected"
    assert derive_validation_status([review("curator", "prediction_only")]) == "insufficient_evidence"
    assert derive_validation_status([review("curator", "supports_indirect"),
                                     review("curator", "conflicting")]) == "conflicting"
