"""Source-specific import adapters.

Each adapter reads one documented file format and converts raw rows into
source-neutral :class:`AssociationRecord` / :class:`TargetRecord` objects.
Adapters do *no* database work and *no* entity resolution; that happens in
:mod:`app.ingestion.pipeline`. New sources are added by writing a new adapter
and registering it in ``ADAPTERS``.
"""
import csv
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..models.constants import EVIDENCE_STRENGTHS, GENE_RELATIONSHIPS, HUMAN, NCRNA_TYPES, REGULATION_DIRECTIONS
from ..normalization.text import clean_pmid, clean_text, split_pmids
from ..validation.evidence import (
    classify_generic,
    classify_hmdd,
    classify_lncrnadisease,
    normalize_association_type,
)

csv.field_size_limit(50 * 1024 * 1024)


@dataclass
class AssociationRecord:
    ncrna_name: str
    ncrna_type: str
    disease_name: str
    source_database: str
    source_record_id: str
    organism: str = HUMAN
    association_type: str = "other"
    regulation_direction: str = "unspecified"
    evidence_level: str = "unverified"
    evidence_rationale: str | None = None
    evidence_text: str | None = None
    experimental_methods: str | None = None
    source_category: str | None = None
    pmids: list = field(default_factory=list)
    source_url: str | None = None
    source_version: str | None = None
    gene_symbol: str | None = None
    gene_entrez_id: str | None = None
    gene_relationship: str | None = None
    gene_evidence: str | None = None
    original_record: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


@dataclass
class TargetRecord:
    ncrna_name: str
    ncrna_type: str
    gene_symbol: str | None
    relationship: str
    source_database: str
    source_record_id: str
    organism: str = HUMAN
    gene_entrez_id: str | None = None
    evidence_strength: str = "not_stated"
    experimental_methods: str | None = None
    evidence_description: str | None = None
    pmids: list = field(default_factory=list)
    original_record: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


@dataclass
class Skip:
    reason: str
    detail: str | None = None


def record_hash(*parts):
    digest = hashlib.sha1("\x1f".join(str(p or "") for p in parts).encode("utf-8")).hexdigest()
    return f"sha1:{digest[:20]}"


class BaseAdapter:
    key = "base"
    kind = "associations"  # or "targets"
    source_database = "unknown"
    description = ""
    delimiter = "\t"
    required_columns = ()
    optional_columns = ()
    documentation_url = None

    # Encodings tried, in order, for each line. Strict UTF-8 by default.
    encodings = ("utf-8",)

    def __init__(self, source_version=None, source_database=None):
        self.source_version = source_version
        if source_database:
            self.source_database = source_database
        self.fallback_decoded_lines = 0

    def _decoded_lines(self, fh):
        for lineno, raw in enumerate(fh, start=1):
            if lineno == 1 and raw.startswith(b"\xef\xbb\xbf"):
                raw = raw[3:]
            for i, enc in enumerate(self.encodings):
                try:
                    text = raw.decode(enc)
                except UnicodeDecodeError:
                    continue
                if i > 0:
                    self.fallback_decoded_lines += 1
                break
            else:
                raise ValueError(f"Line {lineno} is not valid {' / '.join(self.encodings)} text")
            yield text

    def read_rows(self, path):
        """Yield ``(line_number, row_dict)``. Raises ``ValueError`` on missing columns."""
        path = Path(path)
        delimiter = self.delimiter
        if path.suffix.lower() == ".csv":
            delimiter = ","
        with path.open("rb") as fh:
            reader = csv.DictReader(self._decoded_lines(fh), delimiter=delimiter)
            header = [h.strip() for h in (reader.fieldnames or [])]
            reader.fieldnames = header
            missing = [c for c in self.required_columns if c not in header]
            if missing:
                raise ValueError(f"Missing required column(s): {', '.join(missing)}")
            for i, row in enumerate(reader, start=2):
                yield i, {k: v for k, v in row.items() if k is not None}

    def transform(self, row):  # pragma: no cover - abstract
        raise NotImplementedError

    @classmethod
    def describe(cls):
        return {
            "key": cls.key, "kind": cls.kind, "source_database": cls.source_database,
            "description": cls.description, "required_columns": list(cls.required_columns),
            "optional_columns": list(cls.optional_columns), "documentation_url": cls.documentation_url,
        }


class HMDDAdapter(BaseAdapter):
    """HMDD v3.x ``alldata.txt`` (columns: category, mir, disease, pmid, description)."""

    key = "hmdd"
    source_database = "HMDD"
    description = "Human microRNA Disease Database v3.x 'all data' file (experimentally supported miRNA–disease records)."
    required_columns = ("category", "mir", "disease", "pmid", "description")
    documentation_url = "http://www.cuilab.cn/hmdd"
    # The HMDD v3.2 file is mostly UTF-8/ASCII, but some descriptions contain
    # GBK-encoded characters (e.g. Greek letters). Lines are decoded with
    # fallbacks and counted in the import report.
    encodings = ("utf-8", "gb18030", "cp1252", "latin-1")

    def transform(self, row):
        mir, disease = clean_text(row.get("mir")), clean_text(row.get("disease"))
        category = clean_text(row.get("category"))
        if not mir or not disease or not category:
            return Skip("missing_required_field", "mir, disease or category is empty")
        pmid = clean_pmid(row.get("pmid"))
        cls = classify_hmdd(category, pmid)
        if cls is None:
            return Skip("unknown_category", category)
        description = clean_text(row.get("description"))
        return AssociationRecord(
            ncrna_name=mir, ncrna_type="miRNA", disease_name=disease, organism=HUMAN,
            source_database=self.source_database,
            source_record_id=record_hash(category, mir, disease, pmid, description),
            association_type=cls["association_type"], regulation_direction=cls["regulation_direction"],
            evidence_level=cls["evidence_level"], evidence_rationale=cls["rationale"],
            evidence_text=description, source_category=category, pmids=[pmid] if pmid else [],
            source_url="http://www.cuilab.cn/hmdd", source_version=self.source_version,
            original_record=row,
        )


class LncRNADiseaseAdapter(BaseAdapter):
    """LncRNADisease v3.0 ``website_alldata.tsv``."""

    key = "lncrnadisease"
    source_database = "LncRNADisease"
    description = "LncRNADisease v3.0 experimentally supported ncRNA–disease records (lncRNA rows imported; circRNA rows skipped)."
    required_columns = ("ncRNA Symbol", "ncRNA Category", "Species", "Disease Name", "Dysfunction Pattern",
                        "Validated Method", "Description", "PubMed ID")
    optional_columns = ("Sample", "Clinical Application", "Causality", "Causal Description")
    documentation_url = "http://www.rnanut.net/lncrnadisease/"

    def transform(self, row):
        name, disease = clean_text(row.get("ncRNA Symbol")), clean_text(row.get("Disease Name"))
        category = clean_text(row.get("ncRNA Category")) or ""
        if not name or not disease:
            return Skip("missing_required_field", "ncRNA Symbol or Disease Name is empty")
        ncrna_type = {"lncrna": "lncRNA", "mirna": "miRNA"}.get(category.lower())
        if ncrna_type is None:
            return Skip("unsupported_ncrna_class", category or "empty")
        organism = clean_text(row.get("Species")) or "unspecified"
        pmids = split_pmids(row.get("PubMed ID"))
        methods = clean_text(row.get("Validated Method"))
        pattern = clean_text(row.get("Dysfunction Pattern"))
        cls = classify_lncrnadisease(pattern, methods, pmids[0] if pmids else None)
        parts = [clean_text(row.get("Description"))]
        if clean_text(row.get("Causality")) == "Yes":
            parts.append("Causal (source-reported): " + (clean_text(row.get("Causal Description")) or "yes"))
        if clean_text(row.get("Sample")):
            parts.append("Sample: " + clean_text(row.get("Sample")))
        return AssociationRecord(
            ncrna_name=name, ncrna_type=ncrna_type, disease_name=disease, organism=organism,
            source_database=self.source_database,
            source_record_id=record_hash(name, category, organism, disease, pattern, methods,
                                         row.get("PubMed ID"), row.get("Description")),
            association_type=cls["association_type"], regulation_direction=cls["regulation_direction"],
            evidence_level=cls["evidence_level"], evidence_rationale=cls["rationale"],
            evidence_text=" | ".join(p for p in parts if p) or None, experimental_methods=methods,
            source_category=pattern, pmids=pmids, source_url="http://www.rnanut.net/lncrnadisease/",
            source_version=self.source_version, original_record=row,
        )


GENERIC_ASSOCIATION_COLUMNS = ("ncrna_name", "ncrna_type", "disease_name", "source_database")
GENERIC_ASSOCIATION_OPTIONAL = (
    "organism", "pmid", "association_type", "regulation_direction", "evidence_level", "experimental_methods",
    "evidence_description", "source_record_id", "source_url", "source_version", "gene_symbol",
    "gene_entrez_id", "gene_relationship", "gene_evidence",
)


class GenericAssociationAdapter(BaseAdapter):
    """Documented ncRNAAtlas association schema for curated CSV/TSV uploads."""

    key = "generic_associations"
    source_database = "User upload"
    description = "ncRNAAtlas generic ncRNA–disease association schema (see docs/data_sources.md)."
    required_columns = GENERIC_ASSOCIATION_COLUMNS
    optional_columns = GENERIC_ASSOCIATION_OPTIONAL

    def transform(self, row):
        name, disease = clean_text(row.get("ncrna_name")), clean_text(row.get("disease_name"))
        source = clean_text(row.get("source_database"))
        if not name or not disease or not source:
            return Skip("missing_required_field", "ncrna_name, disease_name and source_database are required")
        ncrna_type = {t.lower(): t for t in NCRNA_TYPES}.get((clean_text(row.get("ncrna_type")) or "").lower())
        if ncrna_type is None:
            return Skip("unsupported_ncrna_class", clean_text(row.get("ncrna_type")) or "empty")
        warnings = []
        pmids = split_pmids(row.get("pmid"))
        if clean_text(row.get("pmid")) and not pmids:
            warnings.append(f"Malformed PMID '{row.get('pmid')}' ignored")
        methods = clean_text(row.get("experimental_methods"))
        level, warn = classify_generic(row.get("evidence_level"), methods, pmids[0] if pmids else None)
        if warn:
            warnings.append(warn)
        assoc_type = normalize_association_type(row.get("association_type"))
        if clean_text(row.get("association_type")) and assoc_type is None:
            warnings.append(f"Unknown association_type '{row.get('association_type')}' stored as 'other'")
        direction = (clean_text(row.get("regulation_direction")) or "unspecified").lower()
        if direction not in REGULATION_DIRECTIONS:
            warnings.append(f"Unknown regulation_direction '{direction}' stored as 'unspecified'")
            direction = "unspecified"
        gene_rel = clean_text(row.get("gene_relationship"))
        if gene_rel and gene_rel not in GENE_RELATIONSHIPS:
            warnings.append(f"Unknown gene_relationship '{gene_rel}'; gene link skipped")
            gene_rel = None
        gene_symbol = clean_text(row.get("gene_symbol"))
        if gene_symbol and not gene_rel:
            gene_rel = None if clean_text(row.get("gene_relationship")) else "indirectly_related"
        record_id = clean_text(row.get("source_record_id")) or record_hash(*[row.get(c) for c in sorted(row)])
        return AssociationRecord(
            ncrna_name=name, ncrna_type=ncrna_type, disease_name=disease,
            organism=clean_text(row.get("organism")) or HUMAN, source_database=source,
            source_record_id=record_id, association_type=assoc_type or "other", regulation_direction=direction,
            evidence_level=level, evidence_rationale="Declared/derived from uploaded record",
            evidence_text=clean_text(row.get("evidence_description")), experimental_methods=methods,
            pmids=pmids, source_url=clean_text(row.get("source_url")),
            source_version=clean_text(row.get("source_version")) or self.source_version,
            gene_symbol=gene_symbol if gene_rel else None, gene_entrez_id=clean_text(row.get("gene_entrez_id")),
            gene_relationship=gene_rel, gene_evidence=clean_text(row.get("gene_evidence")),
            original_record=row, warnings=warnings,
        )


GENERIC_TARGET_COLUMNS = ("ncrna_name", "ncrna_type", "gene_symbol", "relationship", "source_database")
GENERIC_TARGET_OPTIONAL = ("organism", "gene_entrez_id", "evidence_strength", "experimental_methods", "pmid",
                           "evidence_description", "source_record_id")


class GenericTargetAdapter(BaseAdapter):
    """Documented ncRNAAtlas ncRNA→gene relationship schema."""

    key = "generic_targets"
    kind = "targets"
    source_database = "User upload"
    description = "ncRNAAtlas generic ncRNA–gene relationship schema (see docs/data_sources.md)."
    required_columns = GENERIC_TARGET_COLUMNS
    optional_columns = GENERIC_TARGET_OPTIONAL

    def transform(self, row):
        name, gene = clean_text(row.get("ncrna_name")), clean_text(row.get("gene_symbol"))
        source = clean_text(row.get("source_database"))
        rel = clean_text(row.get("relationship"))
        if not name or not (gene or clean_text(row.get("gene_entrez_id"))) or not source:
            return Skip("missing_required_field", "ncrna_name, gene_symbol and source_database are required")
        if rel not in GENE_RELATIONSHIPS:
            return Skip("invalid_relationship", rel or "empty")
        ncrna_type = {t.lower(): t for t in NCRNA_TYPES}.get((clean_text(row.get("ncrna_type")) or "").lower())
        if ncrna_type is None:
            return Skip("unsupported_ncrna_class", clean_text(row.get("ncrna_type")) or "empty")
        strength = (clean_text(row.get("evidence_strength")) or "not_stated").lower()
        warnings = []
        if strength not in EVIDENCE_STRENGTHS:
            warnings.append(f"Unknown evidence_strength '{strength}' stored as 'not_stated'")
            strength = "not_stated"
        pmids = split_pmids(row.get("pmid"))
        if rel == "experimentally_validated_target" and not pmids:
            warnings.append("Experimentally validated target without PMID; stored as 'inferred_target'")
            rel = "inferred_target"
        return TargetRecord(
            ncrna_name=name, ncrna_type=ncrna_type, gene_symbol=gene, relationship=rel, source_database=source,
            source_record_id=clean_text(row.get("source_record_id")) or record_hash(*[row.get(c) for c in sorted(row)]),
            organism=clean_text(row.get("organism")) or HUMAN, gene_entrez_id=clean_text(row.get("gene_entrez_id")),
            evidence_strength=strength, experimental_methods=clean_text(row.get("experimental_methods")),
            evidence_description=clean_text(row.get("evidence_description")), pmids=pmids,
            original_record=row, warnings=warnings,
        )


class MiRTarBaseAdapter(BaseAdapter):
    """miRTarBase MTI export (``hsa_MTI``) saved as CSV/TSV.

    Column names follow miRTarBase's published MTI download layout. "Functional
    MTI" rows are strong experimental evidence (reporter assay, western blot,
    qPCR); "(Weak)" rows come from high-throughput methods.
    """

    key = "mirtarbase"
    kind = "targets"
    source_database = "miRTarBase"
    description = "miRTarBase miRNA–target interaction export (hsa_MTI) converted to CSV/TSV."
    required_columns = ("miRTarBase ID", "miRNA", "Species (miRNA)", "Target Gene", "Target Gene (Entrez ID)",
                        "Experiments", "Support Type", "References (PMID)")
    documentation_url = "https://mirtarbase.cuhk.edu.cn/"

    def transform(self, row):
        mirna, gene = clean_text(row.get("miRNA")), clean_text(row.get("Target Gene"))
        if not mirna or not gene:
            return Skip("missing_required_field", "miRNA or Target Gene is empty")
        species = clean_text(row.get("Species (miRNA)")) or "unspecified"
        support = clean_text(row.get("Support Type")) or ""
        pmids = split_pmids(row.get("References (PMID)"))
        strength = "weak" if "weak" in support.lower() else ("strong" if support else "not_stated")
        if "non-functional" in support.lower() and strength != "weak":
            strength = "not_stated"
        rel = "experimentally_validated_target" if pmids else "inferred_target"
        return TargetRecord(
            ncrna_name=mirna, ncrna_type="miRNA", gene_symbol=gene, relationship=rel,
            source_database=self.source_database,
            source_record_id=f"{clean_text(row.get('miRTarBase ID'))}:{pmids[0] if pmids else ''}",
            organism=species, gene_entrez_id=clean_text(row.get("Target Gene (Entrez ID)")),
            evidence_strength=strength, experimental_methods=clean_text(row.get("Experiments")),
            evidence_description=f"miRTarBase support type: {support}" if support else None,
            pmids=pmids, original_record=row,
        )


ADAPTERS = {a.key: a for a in (HMDDAdapter, LncRNADiseaseAdapter, GenericAssociationAdapter,
                               GenericTargetAdapter, MiRTarBaseAdapter)}


def get_adapter(key, **kwargs):
    if key not in ADAPTERS:
        raise KeyError(f"Unknown adapter '{key}'. Available: {', '.join(ADAPTERS)}")
    return ADAPTERS[key](**kwargs)


def json_safe(row):
    return json.loads(json.dumps(row, default=str))
