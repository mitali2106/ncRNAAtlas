"""Import pipeline: resolve → deduplicate → persist with provenance.

Deduplication rules
-------------------
* ncRNA entities are keyed by ``(canonical_name, organism)``; a resolved
  stable identifier (miRBase accession / HGNC ID) is also checked so that two
  source spellings of the same locus become one entity.
* Diseases are keyed by normalized name, and by MeSH descriptor ID when
  resolved. Similar-looking names are never merged.
* Associations are keyed by ``(ncRNA entity, disease entity, association
  type)``. Organism is part of the ncRNA entity key.
* Source records are keyed by ``(association, source_database,
  source_record_id)``; re-importing the same file is idempotent.
* Merging never drops provenance: every source record and every PMID is kept.
"""
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select

from ..extensions import db
from ..models import (
    Alias,
    Association,
    AssociationGene,
    AssociationPublication,
    AssociationSource,
    Disease,
    Gene,
    NcRNA,
    NcRNAGeneInteraction,
    Publication,
    utcnow,
)
from ..normalization.disease import disease_key
from ..normalization.text import normalize_key
from ..services.pubmed import pubmed_url
from ..validation.evidence import aggregate_evidence
from .adapters import AssociationRecord, Skip, TargetRecord, json_safe

log = logging.getLogger(__name__)
MAX_WARNINGS = 500


@dataclass
class ImportResult:
    source_database: str
    dry_run: bool = False
    raw_records: int = 0
    valid_records: int = 0
    inserted: int = 0  # new source records that created a new association / interaction
    updated: int = 0  # new source records merged into an existing association
    unchanged: int = 0  # source record already present (idempotent re-import)
    skipped: int = 0
    skip_reasons: Counter = field(default_factory=Counter)
    duplicates_in_file: int = 0
    merged_into_existing: int = 0
    non_human_records: int = 0
    missing_pmid: int = 0
    new_entities: Counter = field(default_factory=Counter)
    unresolved: dict = field(default_factory=lambda: defaultdict(dict))
    warnings: list = field(default_factory=list)
    preview: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def warn(self, line, message):
        if len(self.warnings) < MAX_WARNINGS:
            self.warnings.append({"line": line, "message": message})

    def to_dict(self):
        return {
            "source_database": self.source_database,
            "dry_run": self.dry_run,
            "raw_records": self.raw_records,
            "valid_records": self.valid_records,
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "skipped": self.skipped,
            "skip_reasons": dict(self.skip_reasons),
            "duplicates_in_file": self.duplicates_in_file,
            "merged_into_existing": self.merged_into_existing,
            "non_human_records": self.non_human_records,
            "missing_pmid": self.missing_pmid,
            "new_entities": dict(self.new_entities),
            "unresolved": {k: [{"name": n, **info} for n, info in sorted(v.items())] for k, v in self.unresolved.items()},
            "warnings": self.warnings,
            "warnings_truncated": len(self.warnings) >= MAX_WARNINGS,
            "errors": self.errors,
            "preview": self.preview,
        }


class ImportPipeline:
    def __init__(self, resolver, *, is_synthetic=False, overrides=None, skip_unresolved=False,
                 human_only=False, publication_cache=None, import_job=None):
        self.resolver = resolver
        self.is_synthetic = is_synthetic
        self.overrides = {k: {normalize_key(a): b for a, b in v.items()} for k, v in (overrides or {}).items()}
        self.skip_unresolved = skip_unresolved
        self.human_only = human_only
        self.publication_cache = publication_cache or {}
        self.job = import_job
        self._res_cache = {}
        self._ncrna_ids = {}
        self._disease_ids = {}
        self._gene_ids = {}
        self._alias_seen = set()

    # ----------------------------------------------------------- resolution
    def _resolve(self, kind, name, *args, **kwargs):
        override = self.overrides.get(kind, {}).get(normalize_key(name))
        target = override or name
        key = (kind, target, args, tuple(sorted(kwargs.items())))
        if key not in self._res_cache:
            fn = {"ncrna": self.resolver.resolve_ncrna, "disease": self.resolver.resolve_disease,
                  "gene": self.resolver.resolve_gene}[kind]
            res = fn(target, *args, **kwargs)
            if res is not None and override:
                res.aliases.append((name, "curator_override", None))
                res.note = f"Curator override: '{name}' mapped to '{override}'. " + (res.note or "")
                if res.status != "resolved":
                    res.status = "resolved"
            self._res_cache[key] = res
        return self._res_cache[key]

    def _track_unresolved(self, result, kind, raw, res):
        if res.status in ("unresolved", "ambiguous"):
            entry = result.unresolved[kind].setdefault(raw, {"status": res.status, "note": res.note, "count": 0})
            entry["count"] += 1

    # ------------------------------------------------------- get-or-create
    def _add_aliases(self, entity_type, entity_id, aliases, source_database):
        for alias, alias_type, namespace in aliases:
            alias = alias[:255]
            key = (entity_type, entity_id, alias, source_database)
            if key in self._alias_seen:
                continue
            self._alias_seen.add(key)
            exists = db.session.execute(
                select(Alias.id).filter_by(entity_type=entity_type, entity_id=entity_id, alias=alias,
                                           source_database=source_database)
            ).first()
            if not exists:
                db.session.add(Alias(entity_type=entity_type, entity_id=entity_id, alias=alias,
                                     alias_normalized=alias.lower(), alias_type=alias_type, namespace=namespace,
                                     source_database=source_database))

    def _get_ncrna(self, res, ncrna_type, organism, source_database, result):
        key = (res.canonical_name.lower(), organism)
        if key in self._ncrna_ids:
            ncrna_id = self._ncrna_ids[key]
        else:
            q = select(NcRNA).where(db.func.lower(NcRNA.canonical_name) == res.canonical_name.lower(),
                                    NcRNA.organism == organism)
            ncrna = db.session.execute(q).scalars().first()
            if ncrna is None and res.stable_identifier:
                ncrna = db.session.execute(
                    select(NcRNA).filter_by(stable_identifier=res.stable_identifier, organism=organism)
                ).scalars().first()
            if ncrna is None:
                ncrna = NcRNA(
                    canonical_name=res.canonical_name, ncrna_type=ncrna_type, organism=organism,
                    stable_identifier=res.stable_identifier, identifier_namespace=res.identifier_namespace,
                    source_database=source_database, resolution_status=res.status, resolution_note=res.note,
                    description=(res.extra or {}).get("full_name"), is_synthetic=self.is_synthetic,
                )
                db.session.add(ncrna)
                db.session.flush()
                result.new_entities["ncrna"] += 1
            elif ncrna.ncrna_type != ncrna_type:
                result.warn(None, f"{res.canonical_name}: type {ncrna_type} conflicts with stored {ncrna.ncrna_type}")
            ncrna_id = ncrna.id
            self._ncrna_ids[key] = ncrna_id
        self._add_aliases("ncrna", ncrna_id, res.aliases, source_database)
        return ncrna_id

    def _get_disease(self, res, source_database, result):
        norm = (res.extra or {}).get("normalized_name") or disease_key(res.canonical_name)
        if norm in self._disease_ids:
            disease_id = self._disease_ids[norm]
        else:
            disease = db.session.execute(select(Disease).filter_by(normalized_name=norm)).scalars().first()
            if disease is None and res.stable_identifier:
                disease = db.session.execute(
                    select(Disease).filter_by(disease_identifier=res.stable_identifier,
                                              identifier_namespace=res.identifier_namespace)
                ).scalars().first()
            if disease is None:
                disease = Disease(
                    canonical_name=res.canonical_name, normalized_name=norm,
                    disease_identifier=res.stable_identifier, identifier_namespace=res.identifier_namespace,
                    resolution_status=res.status, is_synthetic=self.is_synthetic,
                )
                db.session.add(disease)
                db.session.flush()
                result.new_entities["disease"] += 1
            disease_id = disease.id
            self._disease_ids[norm] = disease_id
        self._add_aliases("disease", disease_id, res.aliases, source_database)
        return disease_id

    def _get_gene(self, res, organism, source_database, result):
        key = (res.canonical_name.upper(), organism)
        if key in self._gene_ids:
            gene_id = self._gene_ids[key]
        else:
            gene = db.session.execute(
                select(Gene).where(db.func.upper(Gene.approved_gene_symbol) == res.canonical_name.upper(),
                                   Gene.organism == organism)
            ).scalars().first()
            if gene is None and res.stable_identifier:
                gene = db.session.execute(
                    select(Gene).filter_by(stable_gene_identifier=res.stable_identifier, organism=organism)
                ).scalars().first()
            if gene is None:
                extra = res.extra or {}
                gene = Gene(
                    approved_gene_symbol=res.canonical_name, stable_gene_identifier=res.stable_identifier,
                    identifier_namespace=res.identifier_namespace, hgnc_id=extra.get("hgnc_id"),
                    organism=organism, full_name=extra.get("full_name"), locus_type=extra.get("locus_type"),
                    resolution_status=res.status, is_synthetic=self.is_synthetic,
                )
                db.session.add(gene)
                db.session.flush()
                result.new_entities["gene"] += 1
            gene_id = gene.id
            self._gene_ids[key] = gene_id
        self._add_aliases("gene", gene_id, res.aliases, source_database)
        return gene_id

    def _get_publication(self, pmid, result):
        pub = db.session.execute(select(Publication).filter_by(pmid=pmid)).scalars().first()
        if pub is None:
            pub = Publication(pmid=pmid, publication_url=pubmed_url(pmid), metadata_status="pending")
            meta = self.publication_cache.get(pmid)
            if meta:
                from ..validation.publications import apply_metadata
                apply_metadata(pub, meta)
            db.session.add(pub)
            db.session.flush()
            result.new_entities["publication"] += 1
        return pub

    # ------------------------------------------------------------------ run
    def run(self, adapter, path, dry_run=False, preview_limit=50, progress=None, limit=None):
        """Import ``path`` with ``adapter``. With ``dry_run`` all writes are rolled back."""
        result = ImportResult(source_database=adapter.source_database, dry_run=dry_run)
        seen_records = set()
        touched = set()
        try:
            for line, row in adapter.read_rows(path):
                if limit and result.raw_records >= limit:
                    break
                result.raw_records += 1
                rec = adapter.transform(row)
                if isinstance(rec, Skip):
                    result.skipped += 1
                    result.skip_reasons[rec.reason] += 1
                    result.warn(line, f"Skipped ({rec.reason}): {rec.detail}")
                    continue
                for w in rec.warnings:
                    result.warn(line, w)
                if (rec.source_database, rec.source_record_id) in seen_records:
                    result.duplicates_in_file += 1
                    result.skipped += 1
                    result.skip_reasons["duplicate_in_file"] += 1
                    continue
                seen_records.add((rec.source_database, rec.source_record_id))
                if rec.organism != "Homo sapiens":
                    result.non_human_records += 1
                    if self.human_only:
                        result.skipped += 1
                        result.skip_reasons["non_human"] += 1
                        continue
                if isinstance(rec, AssociationRecord):
                    outcome = self._import_association(rec, line, result, touched)
                else:
                    outcome = self._import_target(rec, line, result)
                if outcome is None:
                    continue
                result.valid_records += 1
                if len(result.preview) < preview_limit:
                    result.preview.append(outcome)
                if progress and result.raw_records % 500 == 0:
                    progress(result)
            self._recompute(touched)
            if adapter.fallback_decoded_lines:
                result.warn(None, f"{adapter.fallback_decoded_lines} line(s) were not valid UTF-8 and were "
                                  f"decoded with fallback encodings ({', '.join(adapter.encodings[1:])})")
            if dry_run:
                db.session.rollback()
            else:
                db.session.commit()
        except ValueError as exc:  # missing columns / malformed file
            db.session.rollback()
            result.errors.append(str(exc))
        except Exception as exc:
            db.session.rollback()
            log.exception("Import failed")
            result.errors.append(f"{exc.__class__.__name__}: {exc}")
        if progress:
            progress(result)
        return result

    def _import_association(self, rec, line, result, touched):
        ncrna_res = self._resolve("ncrna", rec.ncrna_name, rec.ncrna_type, rec.organism)
        disease_res = self._resolve("disease", rec.disease_name)
        if ncrna_res is None or disease_res is None:
            result.skipped += 1
            result.skip_reasons["missing_required_field"] += 1
            return None
        self._track_unresolved(result, "ncrna", rec.ncrna_name, ncrna_res)
        self._track_unresolved(result, "disease", rec.disease_name, disease_res)
        if self.skip_unresolved and (ncrna_res.status in ("unresolved", "ambiguous")
                                     or disease_res.status in ("unresolved", "ambiguous")):
            result.skipped += 1
            result.skip_reasons["unresolved_entity"] += 1
            return None
        if not rec.pmids:
            result.missing_pmid += 1

        ncrna_id = self._get_ncrna(ncrna_res, rec.ncrna_type, rec.organism, rec.source_database, result)
        disease_id = self._get_disease(disease_res, rec.source_database, result)
        assoc = db.session.execute(
            select(Association).filter_by(ncrna_id=ncrna_id, disease_id=disease_id,
                                          association_type=rec.association_type)
        ).scalars().first()
        is_new = assoc is None
        if is_new:
            assoc = Association(ncrna_id=ncrna_id, disease_id=disease_id, association_type=rec.association_type,
                                evidence_level=rec.evidence_level, regulation_direction=rec.regulation_direction,
                                validation_status="not_reviewed", is_synthetic=self.is_synthetic)
            db.session.add(assoc)
            db.session.flush()
        source = db.session.execute(
            select(AssociationSource).filter_by(association_id=assoc.id, source_database=rec.source_database,
                                                source_record_id=rec.source_record_id)
        ).scalars().first()
        if source is not None:
            result.unchanged += 1
            status = "unchanged"
        else:
            db.session.add(AssociationSource(
                association_id=assoc.id, source_database=rec.source_database,
                source_record_id=rec.source_record_id, source_url=rec.source_url,
                source_version=rec.source_version, import_timestamp=utcnow(),
                import_job_id=self.job.id if self.job else None,
                evidence_level=rec.evidence_level, regulation_direction=rec.regulation_direction,
                source_category=rec.source_category, experimental_methods=rec.experimental_methods,
                evidence_text=rec.evidence_text, pmid=rec.pmids[0] if rec.pmids else None,
                original_record=json_safe(rec.original_record),
            ))
            if is_new:
                result.inserted += 1
                status = "new_association"
            else:
                result.updated += 1
                result.merged_into_existing += 1
                status = "merged_into_existing"
            touched.add(assoc.id)

        for pmid in rec.pmids:
            pub = self._get_publication(pmid, result)
            link = db.session.execute(
                select(AssociationPublication).filter_by(association_id=assoc.id, publication_id=pub.id)
            ).scalars().first()
            note = rec.evidence_text[:2000] if rec.evidence_text else None
            if link is None:
                db.session.add(AssociationPublication(association_id=assoc.id, publication_id=pub.id,
                                                      source_databases=rec.source_database, evidence_notes=note))
            elif rec.source_database not in link.source_databases.split("; "):
                link.source_databases = f"{link.source_databases}; {rec.source_database}"

        if rec.gene_symbol or rec.gene_entrez_id:
            gene_res = self._resolve("gene", rec.gene_symbol, rec.organism, entrez_id=rec.gene_entrez_id)
            if gene_res is not None:
                self._track_unresolved(result, "gene", rec.gene_symbol or rec.gene_entrez_id, gene_res)
                gene_id = self._get_gene(gene_res, rec.organism, rec.source_database, result)
                exists = db.session.execute(
                    select(AssociationGene.id).filter_by(association_id=assoc.id, gene_id=gene_id,
                                                         gene_relationship=rec.gene_relationship,
                                                         source_database=rec.source_database)
                ).first()
                if not exists:
                    db.session.add(AssociationGene(
                        association_id=assoc.id, gene_id=gene_id, gene_relationship=rec.gene_relationship,
                        evidence_description=rec.gene_evidence, source_database=rec.source_database,
                        pmid=rec.pmids[0] if rec.pmids else None,
                    ))
        return {
            "line": line, "status": status, "ncrna": ncrna_res.canonical_name,
            "ncrna_resolution": ncrna_res.status, "disease": disease_res.canonical_name,
            "disease_resolution": disease_res.status, "association_type": rec.association_type,
            "evidence_level": rec.evidence_level, "pmids": rec.pmids, "organism": rec.organism,
        }

    def _import_target(self, rec: TargetRecord, line, result):
        ncrna_res = self._resolve("ncrna", rec.ncrna_name, rec.ncrna_type, rec.organism)
        gene_res = self._resolve("gene", rec.gene_symbol, rec.organism, entrez_id=rec.gene_entrez_id)
        if ncrna_res is None or gene_res is None:
            result.skipped += 1
            result.skip_reasons["missing_required_field"] += 1
            return None
        self._track_unresolved(result, "ncrna", rec.ncrna_name, ncrna_res)
        self._track_unresolved(result, "gene", rec.gene_symbol or rec.gene_entrez_id, gene_res)
        if self.skip_unresolved and (ncrna_res.status in ("unresolved", "ambiguous")
                                     or gene_res.status in ("unresolved", "ambiguous")):
            result.skipped += 1
            result.skip_reasons["unresolved_entity"] += 1
            return None
        if not rec.pmids:
            result.missing_pmid += 1
        ncrna_id = self._get_ncrna(ncrna_res, rec.ncrna_type, rec.organism, rec.source_database, result)
        gene_id = self._get_gene(gene_res, rec.organism, rec.source_database, result)
        status = "unchanged"
        for pmid in rec.pmids or [None]:
            exists = db.session.execute(
                select(NcRNAGeneInteraction.id).filter_by(ncrna_id=ncrna_id, gene_id=gene_id,
                                                          relationship=rec.relationship,
                                                          source_database=rec.source_database, pmid=pmid)
            ).first()
            if exists:
                result.unchanged += 1
                continue
            if pmid:
                self._get_publication(pmid, result)
            db.session.add(NcRNAGeneInteraction(
                ncrna_id=ncrna_id, gene_id=gene_id, relationship=rec.relationship,
                evidence_strength=rec.evidence_strength, experimental_methods=rec.experimental_methods,
                evidence_description=rec.evidence_description, source_database=rec.source_database,
                source_record_id=rec.source_record_id, pmid=pmid, original_record=json_safe(rec.original_record),
                is_synthetic=self.is_synthetic,
            ))
            db.session.flush()
            result.inserted += 1
            status = "new_interaction"
        return {"line": line, "status": status, "ncrna": ncrna_res.canonical_name,
                "ncrna_resolution": ncrna_res.status, "gene": gene_res.canonical_name,
                "gene_resolution": gene_res.status, "relationship": rec.relationship, "pmids": rec.pmids}

    def _recompute(self, association_ids):
        """Re-derive association-level evidence from all of its source records."""
        for chunk_start in range(0, len(association_ids), 500):
            ids = list(association_ids)[chunk_start:chunk_start + 500]
            rows = db.session.execute(
                select(AssociationSource.association_id, AssociationSource.evidence_level,
                       AssociationSource.regulation_direction, AssociationSource.evidence_text,
                       AssociationSource.source_database, AssociationSource.pmid)
                .where(AssociationSource.association_id.in_(ids))
            ).all()
            grouped = defaultdict(list)
            for r in rows:
                grouped[r.association_id].append(r._asdict())
            for assoc in db.session.execute(select(Association).where(Association.id.in_(ids))).scalars():
                srcs = grouped.get(assoc.id, [])
                assoc.evidence_level, assoc.regulation_direction = aggregate_evidence(srcs)
                assoc.experimental_evidence_summary = _summary(srcs)


def _summary(sources):
    by_db = Counter(s["source_database"] for s in sources)
    levels = Counter(s["evidence_level"] for s in sources)
    pmids = {s["pmid"] for s in sources if s["pmid"]}
    parts = [", ".join(f"{n} {db_} record{'s' if n > 1 else ''}" for db_, n in sorted(by_db.items()))]
    parts.append(f"{len(pmids)} distinct PMID{'s' if len(pmids) != 1 else ''}")
    parts.append("evidence: " + ", ".join(f"{lvl} ×{n}" for lvl, n in levels.most_common()))
    return "; ".join(parts)
