"""Evidence classification.

Each *source record* is classified on its own content (category, reported
experimental method, PMID). The association-level evidence is then derived
from all of its source records. Classification rules are documented in
``docs/methodology.md`` and are intentionally conservative:

* A record is ``experimental`` only if the source reports an experimental
  observation (an HMDD experimental category, or a LncRNADisease
  "Validated Method") *and* cites a publication.
* HMDD's ``other`` category does not state what kind of evidence was found,
  so it is ``literature_unclear``.
* Records without any PMID or method are ``unverified``.
* Up- and down-regulation reported for the same ncRNA, disease and
  association type by different records is flagged as ``conflicting``.
"""
import re

from ..models.constants import ASSOCIATION_TYPES, EVIDENCE_LEVELS

# HMDD v3 category -> (association_type, regulation_direction)
_HMDD_PREFIXES = [
    ("circulation_biomarker_diagnosis", "circulating_biomarker"),
    ("circulation_biomarker_prognosis", "circulating_biomarker"),
    ("tissue_expression", "expression"),
    ("genetics_gwas", "genetic_variant"),
    ("genetics_overexpression", "functional"),
    ("genetics_knock down", "functional"),
    ("genetics_knockdown", "functional"),
    ("epigenetics", "epigenetic"),
    ("target gene", "target_mediated"),
    ("transcription factor target", "regulatory"),
    ("lncrna target", "regulatory"),
    ("therapeutic target", "therapeutic_target"),
    ("other", "other"),
]


def _direction_from_suffix(category):
    tail = re.split(r"[_\-\s]", category)[-1]
    return {"up": "up", "down": "down", "ns": "not_significant"}.get(tail, "unspecified")


def classify_hmdd(category, pmid):
    cat = (category or "").strip().lower()
    assoc_type = next((t for prefix, t in _HMDD_PREFIXES if cat.startswith(prefix)), None)
    if assoc_type is None:
        return None
    direction = _direction_from_suffix(cat) if assoc_type in ("expression", "circulating_biomarker") else "unspecified"
    if not pmid:
        level, why = "unverified", "No PMID in source record"
    elif assoc_type == "other":
        level, why = "literature_unclear", "HMDD category 'other' does not state the type of evidence"
    else:
        level, why = "experimental", f"HMDD experimental evidence category '{category}'"
    return {"association_type": assoc_type, "regulation_direction": direction,
            "evidence_level": level, "rationale": why}


def classify_lncrnadisease(pattern, methods, pmid):
    p = (pattern or "").strip().lower()
    if p.startswith("expression"):
        assoc_type = "expression"
        if "highly" in p or "up" in p:
            direction = "up"
        elif "lower" in p or "down" in p:
            direction = "down"
        else:
            direction = "unspecified"
    elif p.startswith(("interaction", "regulation", "regulated", "regualtion", "activation")):
        assoc_type, direction = "regulatory", "unspecified"
    elif p.startswith(("mutation", "polymorphism", "locus", "snp")):
        assoc_type, direction = "genetic_variant", "unspecified"
    elif p.startswith("epigenetic"):
        assoc_type, direction = "epigenetic", "unspecified"
    else:
        assoc_type, direction = "other", "unspecified"
    methods = (methods or "").strip()
    if not pmid:
        level, why = "unverified", "No PMID in source record"
    elif methods:
        level, why = "experimental", f"LncRNADisease reports validation method(s): {methods}"
    else:
        level, why = "literature_unclear", "No validation method reported"
    return {"association_type": assoc_type, "regulation_direction": direction,
            "evidence_level": level, "rationale": why}


def classify_generic(evidence_level, methods, pmid):
    """Classification for user-uploaded records (documented TSV schema).

    A declared level is accepted only when the record carries the evidence
    needed to justify it; otherwise it is downgraded and a warning returned.
    """
    declared = (evidence_level or "").strip().lower() or None
    methods = (methods or "").strip()
    warning = None
    if declared and declared not in EVIDENCE_LEVELS:
        warning = f"Unknown evidence_level '{evidence_level}' ignored"
        declared = None
    if declared == "experimental" and not pmid and not methods:
        warning = "Declared 'experimental' without PMID or method; downgraded to 'unverified'"
        declared = "unverified"
    if declared is None:
        if pmid and methods:
            declared = "experimental"
        elif pmid:
            declared = "literature_unclear"
        else:
            declared = "unverified"
    return declared, warning


def normalize_association_type(value):
    v = (value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return v if v in ASSOCIATION_TYPES else None


def aggregate_evidence(source_rows):
    """Derive association-level evidence from its source records.

    ``source_rows`` is an iterable of objects/dicts with ``evidence_level``
    and ``regulation_direction``. Returns ``(evidence_level, direction)``.
    """
    levels, directions = set(), set()
    for row in source_rows:
        get = row.get if isinstance(row, dict) else (lambda k, r=row: getattr(r, k))
        levels.add(get("evidence_level"))
        if get("evidence_level") == "experimental" and get("regulation_direction") in ("up", "down"):
            directions.add(get("regulation_direction"))
    if {"up", "down"} <= directions:
        return "conflicting", "mixed"
    direction = directions.pop() if len(directions) == 1 else None
    for level in ("conflicting", "experimental", "literature_unclear", "computational_prediction"):
        if level in levels:
            return level, direction
    return "unverified", direction
