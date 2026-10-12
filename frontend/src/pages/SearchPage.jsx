import { Link, useSearchParams } from 'react-router-dom'
import SearchBox from '../components/SearchBox'
import { EmptyState, ErrorState, Loading, PageHeader, ResolutionBadge, Section, TypeBadge } from '../components/common'
import { useApi } from '../hooks/useApi'
import { api } from '../services/api'

export default function SearchPage() {
  const [params] = useSearchParams()
  const q = (params.get('q') || '').trim()
  const { data, meta, error, loading, reload } = useApi(() => api.search(q, { limit: 20 }), [q], {
    enabled: q.length >= 2,
  })

  return (
    <>
      <PageHeader eyebrow="Global search" title={q ? `Results for “${q}”` : 'Search'}>
        <p className="muted">Searches canonical names, aliases, identifiers (miRBase, HGNC, MeSH, NCBI Gene), PMIDs and pathway names.</p>
      </PageHeader>
      <SearchBox initial={q} key={q} />
      {q.length > 0 && q.length < 2 && <EmptyState title="Enter at least 2 characters" />}
      {loading && <Loading text="Searching…" />}
      <ErrorState error={error} onRetry={reload} what="search results" />
      {data && meta.total === 0 && (
        <EmptyState title="No matching records">
          Nothing in the ncRNAAtlas database matches “{q}”. Check the spelling, or try an alias or identifier.
        </EmptyState>
      )}
      {data && meta.total > 0 && (
        <div className="results">
          {data.ncrnas?.length > 0 && (
            <Section title={`ncRNAs (${data.ncrnas.length})`}>
              <ul className="result-list">
                {data.ncrnas.map((n) => (
                  <li key={n.id}>
                    <Link to={`/ncrnas/${n.id}`} className="mono">{n.canonical_name}</Link> <TypeBadge type={n.ncrna_type} />
                    <span className="muted small"> {n.organism} · {n.stable_identifier || 'no stable identifier'} · {n.association_count} associations</span>{' '}
                    <ResolutionBadge status={n.resolution_status} />
                  </li>
                ))}
              </ul>
            </Section>
          )}
          {data.diseases?.length > 0 && (
            <Section title={`Diseases (${data.diseases.length})`}>
              <ul className="result-list">
                {data.diseases.map((d) => (
                  <li key={d.id}>
                    <Link to={`/diseases/${d.id}`}>{d.canonical_name}</Link>
                    <span className="muted small"> {d.disease_identifier ? `MeSH ${d.disease_identifier}` : 'no MeSH ID'} · {d.association_count} associations</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}
          {data.genes?.length > 0 && (
            <Section title={`Genes (${data.genes.length})`}>
              <ul className="result-list">
                {data.genes.map((g) => (
                  <li key={g.id}>
                    <Link to={`/genes/${g.id}`} className="mono">{g.approved_gene_symbol}</Link>
                    <span className="muted small"> {g.full_name} {g.stable_gene_identifier && `· NCBI Gene ${g.stable_gene_identifier}`}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}
          {data.publications?.length > 0 && (
            <Section title={`Publications (${data.publications.length})`}>
              <ul className="result-list">
                {data.publications.map((p) => (
                  <li key={p.pmid}>
                    <Link to={`/publications/${p.pmid}`}>PMID {p.pmid}</Link>
                    <span className="small"> {p.publication_title || <em className="muted">metadata not yet retrieved</em>}</span>
                    {p.publication_year && <span className="muted small"> ({p.publication_year})</span>}
                  </li>
                ))}
              </ul>
            </Section>
          )}
          {data.pathways?.length > 0 && (
            <Section title={`KEGG pathways (${data.pathways.length})`}>
              <ul className="result-list">
                {data.pathways.map((p) => (
                  <li key={p.id}>
                    <Link to={`/pathways/${p.id}`}>{p.pathway_name || p.pathway_identifier}</Link>
                    <span className="muted small mono"> {p.pathway_identifier}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </div>
      )}
    </>
  )
}
