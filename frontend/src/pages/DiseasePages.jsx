import { Network } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import AssociationTable from '../components/AssociationTable'
import PathwayList from '../components/PathwayList'
import PublicationList from '../components/PublicationList'
import {
  EmptyState,
  ErrorState,
  EvidenceBadge,
  ExtLink,
  KeyValue,
  Loading,
  PageHeader,
  Pagination,
  ResolutionBadge,
  Section,
} from '../components/common'
import { useApi, useDebounce } from '../hooks/useApi'
import { api } from '../services/api'
import { GENE_RELATIONSHIPS, label } from '../utils/labels'

export function DiseaseList() {
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const dq = useDebounce(q, 300)
  const { data, meta, error, loading, reload } = useApi(() => api.diseases({ q: dq, page, per_page: 25 }), [dq, page])
  return (
    <>
      <PageHeader eyebrow="Explore" title="Diseases">
        <p className="muted">Disease names are kept as reported by the sources and linked to a MeSH descriptor only on an exact label match.</p>
      </PageHeader>
      <div className="filters">
        <input type="search" placeholder="Disease name, synonym or MeSH ID" value={q} maxLength={100}
          onChange={(e) => { setQ(e.target.value); setPage(1) }} aria-label="Search diseases" />
      </div>
      {loading && <Loading />}
      <ErrorState error={error} onRetry={reload} what="diseases" />
      {data && data.length === 0 && <EmptyState title="No diseases match" />}
      {data && data.length > 0 && (
        <Section title="Diseases" subtitle="Sorted by number of associations">
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th scope="col">Disease</th><th scope="col">MeSH</th><th scope="col">Identity</th><th scope="col" className="num">Associations</th></tr></thead>
              <tbody>
                {data.map((d) => (
                  <tr key={d.id}>
                    <td><Link to={`/diseases/${d.id}`}>{d.canonical_name}</Link></td>
                    <td className="mono small">{d.disease_identifier ? <ExtLink href={d.identifier_url}>{d.disease_identifier}</ExtLink> : '—'}</td>
                    <td><ResolutionBadge status={d.resolution_status} /></td>
                    <td className="num">{d.association_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination pagination={meta.pagination} onPage={setPage} />
        </Section>
      )}
    </>
  )
}

export function DiseaseDetail() {
  const { id } = useParams()
  const { data: d, error, loading, reload } = useApi(() => api.disease(id), [id])
  const genes = useApi(() => api.diseaseGenes(id), [id])
  const pathways = useApi(() => api.diseasePathways(id), [id])
  const [pubPage, setPubPage] = useState(1)
  const pubs = useApi(() => api.diseasePublications(id, { page: pubPage, per_page: 10 }), [id, pubPage])
  const [tab, setTab] = useState('miRNA')

  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} what="this disease" />
  return (
    <>
      <PageHeader eyebrow="Disease" title={d.canonical_name}
        actions={<Link to={`/network?focus_type=disease&focus_id=${d.id}`} className="btn"><Network size={16} aria-hidden /> Network</Link>} />
      <div className="grid-2">
        <Section title="Identity">
          <KeyValue items={[
            ['Canonical name', d.canonical_name],
            ['Identifier', d.disease_identifier ? <ExtLink href={d.identifier_url}>{d.identifier_namespace} {d.disease_identifier}</ExtLink> : null],
            ['Identifier resolution', <ResolutionBadge status={d.resolution_status} />],
            ['Names in sources', d.aliases.names.map((a) => a.alias).join('; ') || null],
          ]} />
        </Section>
        <Section title="Evidence summary">
          <KeyValue items={[
            ['Associations', d.counts.associations], ['Associated miRNAs', d.counts.mirnas],
            ['Associated lncRNAs', d.counts.lncrnas], ['Publications', d.counts.publications],
          ]} />
          <ul className="chips">
            {Object.entries(d.counts.evidence_levels).map(([k, v]) => (
              <li key={k}><EvidenceBadge level={k} /> {v}</li>
            ))}
          </ul>
        </Section>
      </div>
      <Section title="Associated ncRNAs"
        actions={
          <div className="tabs" role="tablist">
            {['miRNA', 'lncRNA'].map((t) => (
              <button key={t} type="button" role="tab" aria-selected={tab === t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>
                {t === 'miRNA' ? `miRNAs (${d.counts.mirnas})` : `lncRNAs (${d.counts.lncrnas})`}
              </button>
            ))}
          </div>
        }>
        <AssociationTable key={tab} fetcher={(p) => api.diseaseAssociations(id, p)} deps={[id, tab]} hide={['disease', 'ncrna_type']}
          initialFilters={{ ncrna_type: tab }} emptyText={`No ${tab} associations are recorded for this disease.`} />
      </Section>
      <Section title="Related genes" subtitle="Genes named by a source record for an association with this disease">
        {genes.loading ? <Loading /> : genes.error ? <ErrorState error={genes.error} onRetry={genes.reload} /> :
          genes.data.length === 0 ? <EmptyState title="No association-specific genes recorded" /> : (
            <ul className="result-list">
              {genes.data.map((g) => (
                <li key={`${g.association_id}-${g.gene.id}-${g.gene_relationship}`}>
                  <Link to={`/genes/${g.gene.id}`} className="mono">{g.gene.approved_gene_symbol}</Link>{' '}
                  <span className={`rel rel-${g.gene_relationship}`}>{label(GENE_RELATIONSHIPS, g.gene_relationship)}</span>{' '}
                  of <Link to={`/ncrnas/${g.ncrna.id}`} className="mono">{g.ncrna.canonical_name}</Link> ·{' '}
                  <Link to={`/associations/${g.association_id}`}>evidence</Link>
                  <span className="muted small"> ({g.source_database}{g.pmid ? `, PMID ${g.pmid}` : ''})</span>
                </li>
              ))}
            </ul>
          )}
      </Section>
      <Section title="KEGG pathways (inferred via genes)"><PathwayList state={pathways} /></Section>
      <Section title="Supporting publications"><PublicationList state={pubs} onPage={setPubPage} /></Section>
    </>
  )
}
