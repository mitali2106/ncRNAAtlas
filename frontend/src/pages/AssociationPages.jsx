import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import AssociationTable from '../components/AssociationTable'
import PathwayList from '../components/PathwayList'
import PublicationList from '../components/PublicationList'
import {
  Direction,
  EmptyState,
  ErrorState,
  EvidenceBadge,
  ExtLink,
  KeyValue,
  Loading,
  PageHeader,
  ResolutionBadge,
  Section,
  TypeBadge,
  ValidationBadge,
} from '../components/common'
import { useApi } from '../hooks/useApi'
import { api } from '../services/api'
import { ASSOCIATION_TYPES, GENE_RELATIONSHIPS, REVIEW_OUTCOMES, formatDate, label } from '../utils/labels'

export function AssociationList() {
  return (
    <>
      <PageHeader eyebrow="Explore" title="All associations">
        <p className="muted">Human associations by default. Combine filters; every row links to its evidence.</p>
      </PageHeader>
      <Section title="ncRNA–disease associations">
        <AssociationTable fetcher={(p) => api.associations(p)} emptyText="No associations have been imported yet." />
      </Section>
    </>
  )
}

function SourceRecord({ s }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="source-record">
      <div className="source-head">
        <strong>{s.source_database}</strong>
        <span className="muted small"> {s.source_version} · record {s.source_record_id}</span>{' '}
        <EvidenceBadge level={s.evidence_level} />
      </div>
      <KeyValue items={[
        ['Source category', s.source_category],
        ['Reported direction', <Direction value={s.regulation_direction} />],
        ['Experimental methods', s.experimental_methods],
        ['PMID', s.pmid ? <Link to={`/publications/${s.pmid}`}>{s.pmid}</Link> : null],
        ['Imported', `${formatDate(s.import_timestamp)}${s.import_job_id ? ` (job #${s.import_job_id})` : ''}`],
        ['Source', s.source_url ? <ExtLink href={s.source_url}>{s.source_url}</ExtLink> : null],
      ]} />
      {s.evidence_text && <p className="small evidence-note">“{s.evidence_text}”</p>}
      <button type="button" className="btn btn-small btn-ghost" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        {open ? <ChevronDown size={14} aria-hidden /> : <ChevronRight size={14} aria-hidden />} Original source record
      </button>
      {open && <pre className="code small">{JSON.stringify(s.original_record, null, 2)}</pre>}
    </li>
  )
}

export function AssociationDetail() {
  const { id } = useParams()
  const { data: a, error, loading, reload } = useApi(() => api.association(id), [id])
  const sources = useApi(() => api.associationSources(id), [id])
  const pubs = useApi(() => api.associationPublications(id), [id])

  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} what="this association" />
  const curator = a.reviews.filter((r) => r.review_type === 'curator')
  const triage = a.reviews.filter((r) => r.review_type === 'automated_triage')
  return (
    <>
      <PageHeader eyebrow={`Association #${a.id} · ${label(ASSOCIATION_TYPES, a.association_type)}`}
        title={<><span className="mono">{a.ncrna.canonical_name}</span> <span className="muted">–</span> {a.disease.canonical_name}</>}>
        <div className="badges-row">
          <EvidenceBadge level={a.evidence_level} /> <ValidationBadge status={a.validation_status} />
          {a.is_synthetic && <span className="badge synthetic">Synthetic demonstration record</span>}
        </div>
      </PageHeader>

      <div className="grid-2">
        <Section title="ncRNA">
          <KeyValue items={[
            ['Name', <Link to={`/ncrnas/${a.ncrna.id}`} className="mono">{a.ncrna.canonical_name}</Link>],
            ['Type', <TypeBadge type={a.ncrna.ncrna_type} />],
            ['Identifier', a.ncrna.stable_identifier ? <ExtLink href={a.ncrna.identifier_url}>{a.ncrna.identifier_namespace} {a.ncrna.stable_identifier}</ExtLink> : null],
            ['Organism', a.ncrna.organism],
            ['Identity', <ResolutionBadge status={a.ncrna.resolution_status} />],
          ]} />
        </Section>
        <Section title="Disease">
          <KeyValue items={[
            ['Name', <Link to={`/diseases/${a.disease.id}`}>{a.disease.canonical_name}</Link>],
            ['Identifier', a.disease.disease_identifier ? <ExtLink href={a.disease.identifier_url}>{a.disease.identifier_namespace} {a.disease.disease_identifier}</ExtLink> : null],
            ['Identity', <ResolutionBadge status={a.disease.resolution_status} />],
          ]} />
        </Section>
      </div>

      <Section title="Evidence classification">
        <KeyValue items={[
          ['Association type', `${label(ASSOCIATION_TYPES, a.association_type)} — ${a.association_type_label}`],
          ['Reported direction', <Direction value={a.regulation_direction} />],
          ['Evidence level', <><EvidenceBadge level={a.evidence_level} /> <span className="small muted">{a.evidence_level_label}; derived from all source records below.</span></>],
          ['Curator review', <><ValidationBadge status={a.validation_status} /> <span className="small muted">{a.validation_status_label}</span></>],
          ['Summary', a.experimental_evidence_summary],
          ['Confidence score', a.confidence_score ?? <span className="muted">Not computed — no scoring methodology is applied</span>],
          ['Earliest supporting publication', a.earliest_publication_year],
          ['Last verified', a.last_verified_at ? formatDate(a.last_verified_at) : <span className="muted">Never reviewed by a curator</span>],
        ]} />
      </Section>

      <Section title={`Source records & provenance (${a.source_record_count})`} subtitle="Every claim on this page traces to these records">
        {sources.loading ? <Loading /> : sources.error ? <ErrorState error={sources.error} onRetry={sources.reload} /> : (
          <ul className="source-list">{sources.data.map((s) => <SourceRecord key={s.id} s={s} />)}</ul>
        )}
      </Section>

      <Section title={`Supporting PubMed references (${a.publication_count})`}
        subtitle="Publications cited by the source records. Citation by a source is not, by itself, an independent validation.">
        <PublicationList state={pubs} />
      </Section>

      <Section title="Related genes" subtitle="Genes named by a source record for this specific association">
        {a.genes.length === 0 ? <EmptyState title="No gene is linked to this association by its sources" /> : (
          <ul className="result-list">
            {a.genes.map((g) => (
              <li key={`${g.gene.id}-${g.gene_relationship}-${g.source_database}`}>
                <Link to={`/genes/${g.gene.id}`} className="mono">{g.gene.approved_gene_symbol}</Link>{' '}
                <span className={`rel rel-${g.gene_relationship}`}>{label(GENE_RELATIONSHIPS, g.gene_relationship)}</span>
                <span className="muted small"> {g.source_database}{g.pmid ? ` · PMID ${g.pmid}` : ''}</span>
                {g.evidence_description && <div className="small evidence-note">{g.evidence_description}</div>}
              </li>
            ))}
          </ul>
        )}
        {a.ncrna_gene_relationships.length > 0 && (
          <p className="small muted">
            {a.ncrna.canonical_name} also has {a.ncrna_gene_relationships.length} general (not disease-specific) gene relationship(s):{' '}
            {a.ncrna_gene_relationships.map((r) => r.gene.approved_gene_symbol).filter((v, i, arr) => arr.indexOf(v) === i).join(', ')}.
          </p>
        )}
      </Section>

      <Section title="KEGG pathways"><PathwayList state={{ data: { pathways: a.pathways, gene_count: a.genes.length, notes: a.pathway_note, genes_without_mapping: [] }, loading: false }} /></Section>

      <Section title="Literature review" subtitle="ncRNAAtlas curator decisions (automated hints never change the status)">
        {curator.length === 0 ? <EmptyState title="No curator review recorded">This association has not been independently reviewed.</EmptyState> : (
          <ul className="result-list">
            {curator.map((r) => (
              <li key={r.id}>
                <strong>{label(REVIEW_OUTCOMES, r.outcome)}</strong>{r.pmid && <> · PMID <Link to={`/publications/${r.pmid}`}>{r.pmid}</Link></>}
                <span className="muted small"> · {r.reviewer} · {formatDate(r.reviewed_at)}</span>
                {r.evidence_type && <div className="small">Evidence type: {r.evidence_type}</div>}
                {r.notes && <div className="small evidence-note">{r.notes}</div>}
              </li>
            ))}
          </ul>
        )}
        {triage.length > 0 && (
          <details className="small">
            <summary>Automated triage hints ({triage.length})</summary>
            <ul>
              {triage.map((r) => (
                <li key={r.id}>PMID {r.pmid}: ncRNA mentions {r.flags.ncrna_mentions.join(', ') || 'none'}; disease mentions {r.flags.disease_mentions.join(', ') || 'none'}{r.flags.needs_manual_assessment ? ' — needs manual assessment' : ''}</li>
              ))}
            </ul>
          </details>
        )}
      </Section>
    </>
  )
}

export function PublicationDetail() {
  const { pmid } = useParams()
  const { data: p, meta, error, loading, reload } = useApi(() => api.publication(pmid), [pmid])
  if (loading) return <Loading text="Retrieving publication…" />
  if (error) return <ErrorState error={error} onRetry={reload} what={`PMID ${pmid}`} />
  return (
    <>
      <PageHeader eyebrow={`PubMed ${p.pmid}`} title={p.publication_title || `PMID ${p.pmid}`}>
        <p className="muted">{p.authors}</p>
      </PageHeader>
      {meta.external_note && <p className="banner-sample">{meta.external_note}</p>}
      <Section title="Bibliographic record">
        <KeyValue items={[
          ['Journal', p.journal], ['Year', p.publication_year],
          ['PubMed', <ExtLink href={p.publication_url}>{p.publication_url}</ExtLink>],
          ['DOI', p.doi ? <ExtLink href={p.doi_url}>{p.doi}</ExtLink> : null],
          ['Metadata', `${p.metadata_status}${p.fetched_at ? ` · retrieved ${formatDate(p.fetched_at)}` : ''}`],
        ]} />
        {p.abstract && <><h3 className="h3">Abstract</h3><p className="abstract">{p.abstract}</p></>}
      </Section>
      <Section title="Associations citing this publication">
        {p.associations.length === 0 ? <EmptyState title="Not cited by any stored association" /> : (
          <ul className="result-list">
            {p.associations.map((a) => (
              <li key={a.id}>
                <Link to={`/associations/${a.id}`}>{a.ncrna.canonical_name} – {a.disease.canonical_name}</Link>{' '}
                <span className="small muted">{label(ASSOCIATION_TYPES, a.association_type)} · cited by {a.cited_by_sources.join(', ')}</span>{' '}
                <EvidenceBadge level={a.evidence_level} />
              </li>
            ))}
          </ul>
        )}
      </Section>
    </>
  )
}
