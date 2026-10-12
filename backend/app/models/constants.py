"""Controlled vocabularies used throughout ncRNAAtlas.

Evidence categories, validation statuses and gene relationship types are
deliberately kept separate from source database names: an entry in a
database is not, by itself, proof of experimental validation.
"""

NCRNA_TYPES = ("miRNA", "lncRNA")
HUMAN = "Homo sapiens"

# What kind of evidence the *source record(s)* report.
EVIDENCE_LEVELS = {
    "experimental": "Experimentally supported (as reported by the source)",
    "computational_prediction": "Computationally predicted",
    "literature_unclear": "Literature-supported, validation unclear",
    "conflicting": "Conflicting evidence",
    "unverified": "Unverified",
}

# Outcome of ncRNAAtlas' own literature-review workflow (independent of the source).
VALIDATION_STATUSES = {
    "not_reviewed": "Not yet reviewed by a curator",
    "under_review": "Queued for curator review",
    "curator_confirmed": "Curator confirmed direct experimental support",
    "insufficient_evidence": "Curator found the evidence insufficient or indirect",
    "conflicting": "Curator found conflicting evidence",
    "curator_rejected": "Curator found the publication(s) do not support the association",
}

ASSOCIATION_TYPES = {
    "expression": "Differential expression in disease tissue or cells",
    "circulating_biomarker": "Circulating (body-fluid) diagnostic or prognostic biomarker",
    "genetic_variant": "Genetic variant / mutation / GWAS association",
    "epigenetic": "Epigenetic regulation",
    "functional": "Functional (gain/loss-of-function) evidence",
    "target_mediated": "Disease mechanism mediated by a target gene",
    "regulatory": "Molecular interaction or regulatory relationship",
    "therapeutic_target": "Proposed therapeutic target",
    "other": "Other / unspecified",
}

REGULATION_DIRECTIONS = ("up", "down", "not_significant", "unspecified")

GENE_RELATIONSHIPS = {
    "experimentally_validated_target": "Experimentally validated target of the ncRNA",
    "inferred_target": "Target inferred from source text or indirect evidence",
    "disease_associated_gene": "Gene associated with the disease in the source record",
    "indirectly_related": "Indirectly related gene (e.g. interaction partner, pathway member)",
}

EVIDENCE_STRENGTHS = ("strong", "weak", "not_stated")

REVIEW_OUTCOMES = {
    "supports_direct_experimental": "Publication directly and experimentally supports the association",
    "supports_indirect": "Publication supports the association only indirectly",
    "prediction_only": "Publication reports a computational prediction only",
    "does_not_support": "Publication does not support the association",
    "insufficient": "Evidence insufficient to decide",
    "conflicting": "Publication contradicts other evidence",
}

REVIEW_TYPES = ("curator", "automated_triage")

RESOLUTION_STATUSES = ("resolved", "ambiguous", "unresolved", "not_attempted")

IMPORT_STATUSES = ("pending", "running", "completed", "completed_with_errors", "failed")
