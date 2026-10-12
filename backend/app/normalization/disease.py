"""Disease name normalization.

Disease names are cleaned but never re-worded: two names are only merged if
they are identical after case/whitespace normalization or resolve to the same
ontology identifier (MeSH descriptor).
"""
from .text import clean_text, normalize_key


def clean_disease_name(name):
    return clean_text(name)


def disease_key(name):
    return normalize_key(name)
