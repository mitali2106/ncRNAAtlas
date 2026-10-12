import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  EmptyState,
  ErrorState,
  EvidenceBadge,
  ExtLink,
  KeyValue,
  Loading,
  PageHeader,
  Pagination,
  Section,
  TypeBadge,
} from '../components/common'
import { useApi, useDebounce } from '../hooks/useApi'
import { api } from '../services/api'
import { GENE_RELATIONSHIPS, formatDate, label } from '../utils/labels'

export function PathwayList() {
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const dq = useDebounce(q, 300)
  const { data, meta, error, loading, reload } = useApi(() => api.pathways({ q: dq, page, per_page: 25 }), [dq, page])
  return (
    <>
      <PageHeader eyebrow="Explore" title="KEGG pathways">
        <p className="muted">Only pathways that contain at least one gene stored in ncRNAAtlas are listed. Membership is as reported by the KEGG REST API.</p>
      </PageHeader>
      <div className="filters">
        <input type="search" placeholder="Pathway name or ID (e.g. hsa05206)" value={q} maxLength={100}
          onChange={(e) => { setQ(e.target.value); setPage(1) }} aria-label="Search pathways" />
      </div>
      {loading && <Loading />}
      <ErrorState error={error} onRetry={reload} what="pathways" />
      {data && data.length === 0 && (
        <EmptyState title={dq ? 'No pathways match' : 'No pathway mappings yet'}>
          {!dq && 'Run python scripts/map_pathways.py to map genes to KEGG pathways.'}
        </EmptyState>
      )}
      {data && data.length > 0 && (
        <Section title="Pathways" subtitle="Sorted by number of mapped atlas genes">
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th scope="col">Pathway</th><th scope="col">KEGG ID</th><th scope="col">Organism</th><th scope="col" className="num">Atlas genes</th></tr></thead>
              <tbody>
                {data.map((p) => (
                  <tr key={p.id}>
                    <td><Link to={`/pathways/${p.id}`}>{p.pathway_name || p.pathway_identifier}</Link></td>
                    <td className="mono small"><ExtLink href={p.pathway_url}>{p.pathway_identifier}</ExtLink></td>
                    <td className="small">{p.organism}</td>
                    <td className="num">{p.gene_count}</td>
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

export function PathwayDetail() {
  const { id } = useParams()
  const { data: p, error, loading, reload } = useApi(() => api.pathway(id), [id])
  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} what="this pathway" />
  return (
    <>
      <PageHeader eyebrow={`KEGG pathway · ${p.organism}`} title={p.pathway_name || p.pathway_identifier}>
        <p className="muted small">{p.notes}</p>
      </PageHeader>
      <div className="grid-2">
        <Section title="Pathway">
          <KeyValue items={[
            ['Name', p.pathway_name], ['Identifier', <span className="mono">{p.pathway_identifier}</span>],
            ['Database', p.pathway_database], ['Organism', p.organism],
            ['KEGG record & diagram', <ExtLink href={p.pathway_url}>{p.pathway_url}</ExtLink>],
          ]} />
        </Section>
        <Section title={`Atlas genes mapped to this pathway (${p.genes.length})`}>
          <ul className="chips">
            {p.genes.map((g) => (
              <li key={g.id} title={`${g.full_name || ''} · ${g.mapping_source} · ${formatDate(g.mapped_at)}`}>
                <Link to={`/genes/${g.id}`} className="mono">{g.approved_gene_symbol}</Link>
              </li>
            ))}
          </ul>
          <p className="small muted">Only genes present in ncRNAAtlas are shown; the full membership is on the KEGG page.</p>
        </Section>
      </div>
      <Section title="Related ncRNAs" subtitle="ncRNAs with a stored relationship to a member gene">
        {p.related_ncrnas.length === 0 ? <EmptyState title="None" /> : (
          <ul className="result-list">
            {p.related_ncrnas.map((n) => (
              <li key={`${n.id}-${n.via_gene}-${n.relationship}`}>
                <Link to={`/ncrnas/${n.id}`} className="mono">{n.canonical_name}</Link> <TypeBadge type={n.ncrna_type} />
                <span className="small muted"> via {n.via_gene} ({label(GENE_RELATIONSHIPS, n.relationship)})</span>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section title="Related ncRNA–disease associations" subtitle="Associations whose source record names a member gene">
        {p.related_associations.length === 0 ? <EmptyState title="None" /> : (
          <ul className="result-list">
            {p.related_associations.map((a) => (
              <li key={`${a.id}-${a.via_gene}`}>
                <Link to={`/associations/${a.id}`}>{a.ncrna.canonical_name} – {a.disease.canonical_name}</Link>{' '}
                <EvidenceBadge level={a.evidence_level} />
                <span className="small muted"> via {a.via_gene} ({label(GENE_RELATIONSHIPS, a.gene_relationship)})</span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </>
  )
}
