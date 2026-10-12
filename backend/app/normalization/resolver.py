"""Entity resolution: map raw source names to canonical entities.

Every resolution carries an explicit status (``resolved``, ``ambiguous``,
``unresolved`` or ``not_attempted``) and the original name is always kept as
an alias. Nothing is merged on visual similarity: miRNAs and lncRNAs are
resolved through HGNC (approved symbol, then *unique* previous symbol, then
*unique* alias), genes likewise, and diseases through exact MeSH descriptor
labels only.
"""
import logging
import re
from dataclasses import dataclass, field

from ..models.constants import HUMAN
from ..services.http_client import ExternalServiceError
from .disease import clean_disease_name, disease_key
from .mirna import parse_mirna
from .text import clean_text

log = logging.getLogger(__name__)


@dataclass
class Resolution:
    canonical_name: str
    status: str
    stable_identifier: str | None = None
    identifier_namespace: str | None = None
    note: str | None = None
    # (alias, alias_type, namespace)
    aliases: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    @property
    def is_resolved(self):
        return self.status == "resolved"


class EntityResolver:
    def __init__(self, hgnc_index=None, mesh_cache=None, mesh_service=None, on_mesh_lookup=None,
                 retry_mesh_misses=False):
        self.hgnc = hgnc_index
        self.mesh_cache = mesh_cache if mesh_cache is not None else {}
        self.mesh_service = mesh_service  # None => cache-only
        self.on_mesh_lookup = on_mesh_lookup
        self.mesh_errors = 0
        # Re-query names cached as "no match" (e.g. after the matching rules were extended).
        self.retry_mesh_misses = retry_mesh_misses

    # ------------------------------------------------------------------ ncRNA
    def resolve_ncrna(self, name, ncrna_type, organism=HUMAN):
        raw = clean_text(name)
        if not raw:
            return None
        if ncrna_type == "miRNA":
            return self._resolve_mirna(raw, organism)
        return self._resolve_lncrna(raw, organism)

    def _resolve_mirna(self, raw, organism):
        parsed = parse_mirna(raw, organism)
        if parsed is None:
            return Resolution(raw, "unresolved", note="Name does not follow miRBase nomenclature",
                              aliases=[(raw, "source_name", None)])
        canonical = parsed.precursor_name
        aliases = [(raw, "mature_product" if parsed.is_mature else "source_name", None)]
        if organism != HUMAN or parsed.species != "hsa":
            return Resolution(canonical, "not_attempted", aliases=aliases,
                              note="Identifier resolution is implemented for human miRNAs only")
        if self.hgnc is None:
            return Resolution(canonical, "unresolved", aliases=aliases, note="No HGNC reference loaded")

        symbol = parsed.hgnc_symbol
        record = self.hgnc.by_symbol.get(symbol)
        via_legacy_name = False
        if record is None:
            loci = self.hgnc.mirna_loci(parsed.hgnc_base) if not parsed.locus else []
            if len(loci) == 1:
                record = self.hgnc.by_symbol[loci[0]]
            elif len(loci) > 1:
                return Resolution(
                    canonical, "ambiguous", aliases=aliases,
                    note=f"Name does not specify a genomic locus; candidate loci: {', '.join(loci)}",
                    extra={"candidates": loci},
                )
            else:
                # Legacy miRBase IDs (e.g. hsa-mir-122a, renamed hsa-mir-122) are recorded by
                # HGNC as alias symbols; accept only a unique miRNA-locus match.
                legacy = [r for r in self.hgnc.by_alias.get(parsed.precursor_name.upper(), []) if r.is_mirna]
                if len(legacy) != 1:
                    return Resolution(canonical, "unresolved", aliases=aliases,
                                      note=f"No approved HGNC miRNA locus {symbol}")
                record, via_legacy_name = legacy[0], True
                aliases.append((parsed.precursor_name, "previous_symbol", "miRBase (via HGNC alias)"))
        # Canonical name = current miRBase-style ID derived from the approved HGNC symbol
        # (HGNC alias lists may also contain retired names such as hsa-mir-122a).
        derived = hgnc_symbol_to_mirbase_name(record.symbol)
        if derived is None:
            return Resolution(canonical, "ambiguous", aliases=aliases,
                              note=f"HGNC symbol {record.symbol} does not follow miRNA locus nomenclature")
        canonical = derived
        aliases += [(record.symbol, "synonym", "HGNC"), (record.hgnc_id, "identifier", "HGNC")]
        aliases += [(urs, "identifier", "RNAcentral") for urs in record.rna_central_ids]
        if record.mirbase:
            aliases.append((record.mirbase, "identifier", "miRBase"))
        return Resolution(
            canonical,
            "resolved",
            stable_identifier=record.mirbase or record.hgnc_id,
            identifier_namespace="miRBase" if record.mirbase else "HGNC",
            note=f"Legacy name {parsed.precursor_name} resolved via HGNC alias of {record.symbol}"
            if via_legacy_name else None,
            aliases=_dedupe_aliases(aliases, canonical),
            extra=_hgnc_extra(record),
        )

    def _resolve_lncrna(self, raw, organism):
        aliases = [(raw, "source_name", None)]
        if organism != HUMAN:
            return Resolution(raw, "not_attempted", aliases=aliases,
                              note="Identifier resolution is implemented for human lncRNAs only")
        if self.hgnc is None:
            return Resolution(raw, "unresolved", aliases=aliases, note="No HGNC reference loaded")
        record, method, candidates = self.hgnc.lookup(raw)
        if record is None:
            if candidates:
                return Resolution(raw, "ambiguous", aliases=aliases,
                                  note=f"{method}: {', '.join(c.symbol for c in candidates)}",
                                  extra={"candidates": [c.symbol for c in candidates]})
            return Resolution(raw, "unresolved", aliases=aliases, note="Symbol not found in HGNC")
        if not record.is_noncoding:
            return Resolution(raw, "unresolved", aliases=aliases,
                              note=f"HGNC symbol {record.symbol} is a {record.locus_group}; not merged")
        if method != "approved_symbol":
            aliases.append((raw, "previous_symbol" if method == "previous_symbol" else "synonym", "HGNC"))
        aliases += [(record.hgnc_id, "identifier", "HGNC")]
        aliases += [(urs, "identifier", "RNAcentral") for urs in record.rna_central_ids]
        aliases += [(a, "synonym", "HGNC") for a in record.alias_symbols[:15]]
        return Resolution(
            record.symbol, "resolved", stable_identifier=record.hgnc_id, identifier_namespace="HGNC",
            note=None if method == "approved_symbol" else f"Resolved via HGNC {method.replace('_', ' ')}",
            aliases=_dedupe_aliases(aliases, record.symbol), extra=_hgnc_extra(record),
        )

    # ------------------------------------------------------------------- gene
    def resolve_gene(self, symbol, organism=HUMAN, entrez_id=None):
        raw = clean_text(symbol)
        entrez_id = clean_text(entrez_id)
        if not raw and not entrez_id:
            return None
        aliases = [(raw, "source_name", None)] if raw else []
        if organism != HUMAN:
            return Resolution(raw or entrez_id, "not_attempted", aliases=aliases,
                              note="Gene normalization is implemented for human genes only")
        if self.hgnc is None:
            return Resolution(raw or entrez_id, "unresolved", aliases=aliases, note="No HGNC reference loaded")
        record, method, candidates = None, None, []
        if entrez_id and entrez_id in self.hgnc.by_entrez:
            record, method = self.hgnc.by_entrez[entrez_id], "entrez_id"
            if raw and raw.upper() != record.symbol.upper():
                aliases.append((raw, "synonym", "source"))
        elif raw:
            record, method, candidates = self.hgnc.lookup(raw)
        if record is None:
            if candidates:
                return Resolution(raw, "ambiguous", aliases=aliases,
                                  note=f"{method}: {', '.join(c.symbol for c in candidates)}")
            return Resolution(raw or entrez_id, "unresolved", aliases=aliases, note="Gene not found in HGNC")
        aliases.append((record.hgnc_id, "identifier", "HGNC"))
        if record.entrez_id:
            aliases.append((record.entrez_id, "identifier", "NCBIGene"))
        aliases += [(a, "synonym", "HGNC") for a in record.alias_symbols[:15]]
        aliases += [(p, "previous_symbol", "HGNC") for p in record.prev_symbols[:15]]
        return Resolution(
            record.symbol, "resolved",
            stable_identifier=record.entrez_id, identifier_namespace="NCBIGene" if record.entrez_id else None,
            note=None if method in ("approved_symbol", "entrez_id") else f"Resolved via HGNC {method.replace('_', ' ')}",
            aliases=_dedupe_aliases(aliases, record.symbol), extra=_hgnc_extra(record),
        )

    # ---------------------------------------------------------------- disease
    def resolve_disease(self, name):
        raw = clean_disease_name(name)
        if not raw:
            return None
        key = disease_key(raw)
        hit = self._mesh(raw)
        if hit:
            via_term = hit.get("matched_via") == "entry_term"
            return Resolution(
                hit["label"], "resolved", stable_identifier=hit["id"], identifier_namespace="MeSH",
                note=f"Exact MeSH entry term of descriptor {hit['id']}" if via_term else None,
                aliases=_dedupe_aliases([(raw, "source_name", None), (hit["id"], "identifier", "MeSH")], hit["label"]),
                extra={"normalized_name": disease_key(hit["label"])},
            )
        return Resolution(raw, "unresolved", aliases=[(raw, "source_name", None)],
                          note="No exact MeSH descriptor or entry-term match", extra={"normalized_name": key})

    def _mesh(self, label):
        key = label.lower()
        if key in self.mesh_cache and not (self.retry_mesh_misses and self.mesh_cache[key] is None):
            return self.mesh_cache[key]
        if self.mesh_service is None:
            return None
        try:
            hit = self.mesh_service.lookup_descriptor(label)
        except ExternalServiceError as exc:
            self.mesh_errors += 1
            log.warning("MeSH lookup failed for %r: %s", label, exc.message)
            return None
        self.mesh_cache[key] = hit
        if self.on_mesh_lookup:
            self.on_mesh_lookup(key, hit)
        return hit


_HGNC_MIR = re.compile(r"^MIR(LET)?(\d+)([A-Z]?)(?:-?(\d+))?$")


def hgnc_symbol_to_mirbase_name(symbol):
    """``MIR21`` → ``hsa-mir-21``, ``MIR125B1`` → ``hsa-mir-125b-1``, ``MIRLET7A1`` → ``hsa-let-7a-1``."""
    m = _HGNC_MIR.match(symbol.upper())
    if not m:
        return None
    let, digits, letter, locus = m.groups()
    name = f"hsa-{'let' if let else 'mir'}-{digits}{letter.lower()}"
    return f"{name}-{locus}" if locus else name


def _hgnc_extra(record):
    return {
        "hgnc_id": record.hgnc_id,
        "entrez_id": record.entrez_id,
        "full_name": record.name,
        "locus_type": record.locus_type,
        "rnacentral_ids": record.rna_central_ids,
    }


def _dedupe_aliases(aliases, canonical):
    seen, out = set(), []
    for alias, alias_type, ns in aliases:
        if not alias:
            continue
        key = (alias.lower(), ns)
        if key in seen or (alias == canonical and alias_type == "synonym"):
            continue
        seen.add(key)
        out.append((alias, alias_type, ns))
    return out
