import { Network } from 'lucide-react'
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
  ResolutionBadge,
  Section,
  TypeBadge,
} from '../components/common'
import { useApi, useDebounce } from '../hooks/useApi'
import { api } from '../services/api'
import { ASSOCIATION_TYPES, GENE_RELATIONSHIPS, label } from '../utils/labels'

export function GeneList() {
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const dq = useDebounce(q, 300)
  const { data, meta, error, loading, reload } = useApi(() => api.genes({ q: dq, page, per_page: 25 }), [dq, page])
  return (
    <>
      <PageHeader eyebrow="Explore" title="Genes">
        <p className="muted">Genes are normalized to HGNC-approved symbols and NCBI Gene IDs; original symbols are kept as aliases.</p>
      </PageHeader>
      <div className="filters">
        <input type="search" placeholder="Symbol, alias, name or NCBI Gene ID" value={q} maxLength={100}
          onChange={(e) => { setQ(e.target.value); setPage(1) }} aria-label="Search genes" />
      </div>
      {loading && <Loading />}
      <ErrorState error={error} onRetry={reload} what="genes" />
      {data && data.length === 0 && <EmptyState title="No genes match">Genes enter the atlas through ncRNA–gene relationships and association records.</EmptyState>}
      {data && data.length > 0 && (
        <Section title="Genes">
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th scope="col">Symbol</th><th scope="col">Name</th><th scope="col">NCBI Gene</th><th scope="col" className="num">ncRNAs</th><th scope="col" className="num">KEGG pathways</th></tr></thead>
              <tbody>
                {data.map((g) => (
                  <tr key={g.id}>
                    <td><Link to={`/genes/${g.id}`} className="mono">{g.approved_gene_symbol}</Link></td>
                    <td className="small">{g.full_name || '—'}</td>
                    <td className="mono small">{g.stable_gene_identifier ? <ExtLink href={g.identifier_url}>{g.stable_gene_identifier}</ExtLink> : '—'}</td>
                    <td className="num">{g.ncrna_count}</td>
                    <td className="num">{g.pathway_count}</td>
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

export function GeneDetail() {
  const { id } = useParams()
  const { data: g, error, loading, reload } = useApi(() => api.gene(id), [id])
  const [page, setPage] = useState(1)
  const assoc = useApi(() => api.geneAssociations(id, { page, per_page: 15 }), [id, page])
  const pw = useApi(() => api.genePathways(id), [id])
  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} what="this gene" />
  return (
    <>
      <PageHeader eyebrow={`Gene · ${g.organism}`} title={<span className="mono">{g.approved_gene_symbol}</span>}
        actions={<Link to={`/network?focus_type=gene&focus_id=${g.id}`} className="btn"><Network size={16} aria-hidden /> Network</Link>}>
        {g.full_name && <p className="muted">{g.full_name}</p>}
      </PageHeader>
      <div className="grid-2">
        <Section title="Identity">
          <KeyValue items={[
            ['Approved symbol', <span className="mono">{g.approved_gene_symbol}</span>],
            ['NCBI Gene ID', g.stable_gene_identifier ? <ExtLink href={g.identifier_url}>{g.stable_gene_identifier}</ExtLink> : null],
            ['HGNC ID', g.hgnc_id ? <ExtLink href={g.hgnc_url}>{g.hgnc_id}</ExtLink> : null],
            ['Locus type', g.locus_type],
            ['Normalization', <ResolutionBadge status={g.resolution_status} />],
            ['Synonyms', g.aliases.names.filter((a) => a.alias_type !== 'source_name').map((a) => a.alias).join(', ') || null],
          ]} />
        </Section>
        <Section title="KEGG pathways" subtitle="Direct gene-to-pathway mapping reported by KEGG">
          {pw.loading ? <Loading /> : pw.error ? <ErrorState error={pw.error} onRetry={pw.reload} /> :
            pw.data.length === 0 ? (
              <EmptyState title={pw.meta.mapping_status === 'not_mappable' ? 'Not mappable (no NCBI Gene ID)' : 'No KEGG pathway mapping available'} />
            ) : (
              <ul className="result-list">
                {pw.data.map((p) => (
                  <li key={p.id}>
                    <Link to={`/pathways/${p.id}`}>{p.pathway_name || p.pathway_identifier}</Link>{' '}
                    <span className="mono small"><ExtLink href={p.pathway_url}>{p.pathway_identifier}</ExtLink></span>
                  </li>
                ))}
              </ul>
            )}
        </Section>
      </div>
      <Section title="Associated ncRNAs" subtitle="General ncRNA–gene relationships (not disease-specific)">
        {g.ncrna_relationships.length === 0 ? <EmptyState title="No ncRNA relationships recorded" /> : (
          <div className="table-wrap">
            <table className="table compact">
              <thead><tr><th scope="col">ncRNA</th><th scope="col">Relationship</th><th scope="col">Strength</th><th scope="col">Methods</th><th scope="col">Source record</th><th scope="col">PMID</th></tr></thead>
              <tbody>
                {g.ncrna_relationships.map((r) => (
                  <tr key={r.id}>
                    <td><Link to={`/ncrnas/${r.ncrna.id}`} className="mono">{r.ncrna.canonical_name}</Link> <TypeBadge type={r.ncrna.ncrna_type} /></td>
                    <td><span className={`rel rel-${r.relationship}`}>{label(GENE_RELATIONSHIPS, r.relationship)}</span></td>
                    <td className="small">{r.evidence_strength.replace('_', ' ')}</td>
                    <td className="small">{r.experimental_methods || '—'}</td>
                    <td className="small">{r.source_database}{r.source_record_id ? ` · ${r.source_record_id}` : ''}</td>
                    <td>{r.pmid ? <Link to={`/publications/${r.pmid}`}>{r.pmid}</Link> : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
      <Section title="Related diseases">
        {assoc.loading ? <Loading /> : assoc.error ? <ErrorState error={assoc.error} onRetry={assoc.reload} /> : (
          <>
            <h3 className="h3">Direct: gene named in an association record</h3>
            {assoc.data.direct.length === 0 ? <EmptyState title="No association record names this gene" /> : (
              <ul className="result-list">
                {assoc.data.direct.map((l) => (
                  <li key={`${l.association.id}-${l.gene_relationship}`}>
                    <Link to={`/associations/${l.association.id}`}>{l.association.ncrna.canonical_name} – {l.association.disease.canonical_name}</Link>{' '}
                    <span className={`rel rel-${l.gene_relationship}`}>{label(GENE_RELATIONSHIPS, l.gene_relationship)}</span>
                    <span className="muted small"> {l.source_database}{l.pmid ? ` · PMID ${l.pmid}` : ''}</span>
                    {l.evidence_description && <div className="small evidence-note">{l.evidence_description}</div>}
                  </li>
                ))}
              </ul>
            )}
            <h3 className="h3">Indirect: diseases of ncRNAs related to this gene</h3>
            <p className="small muted">These are connections through an ncRNA only — not evidence that {g.approved_gene_symbol} is involved in the disease.</p>
            {assoc.data.via_ncrna_relationships.length === 0 ? <EmptyState title="None" /> : (
              <div className="table-wrap">
                <table className="table compact">
                  <thead><tr><th scope="col">ncRNA</th><th scope="col">Disease</th><th scope="col">Type</th><th scope="col">Evidence</th><th scope="col" className="num">PMIDs</th></tr></thead>
                  <tbody>
                    {assoc.data.via_ncrna_relationships.map((a) => (
                      <tr key={a.id}>
                        <td className="mono"><Link to={`/ncrnas/${a.ncrna.id}`}>{a.ncrna.canonical_name}</Link></td>
                        <td><Link to={`/associations/${a.id}`}>{a.disease.canonical_name}</Link></td>
                        <td className="small">{label(ASSOCIATION_TYPES, a.association_type)}</td>
                        <td><EvidenceBadge level={a.evidence_level} /></td>
                        <td className="num">{a.publication_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <Pagination pagination={assoc.meta.pagination} onPage={setPage} />
          </>
        )}
      </Section>
    </>
  )
}
