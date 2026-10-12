import { Link } from 'react-router-dom'
import { EmptyState, ErrorState, ExtLink, Loading, Pagination } from './common'

export function PublicationItem({ p }) {
  return (
    <li className="pub">
      <div className="pub-title">
        {p.publication_title ? (
          <Link to={`/publications/${p.pmid}`}>{p.publication_title}</Link>
        ) : (
          <Link to={`/publications/${p.pmid}`}>PMID {p.pmid}</Link>
        )}
      </div>
      <div className="small muted">
        {p.authors && <span>{p.authors.split(', ').slice(0, 3).join(', ')}{p.authors.split(', ').length > 3 ? ' et al.' : ''} · </span>}
        {p.journal && <em>{p.journal}</em>} {p.publication_year && `(${p.publication_year})`}
        {p.metadata_status !== 'fetched' && <span> Metadata {p.metadata_status === 'pending' ? 'not yet retrieved' : p.metadata_status.replace('_', ' ')}.</span>}
      </div>
      <div className="small">
        <ExtLink href={p.publication_url}>PubMed {p.pmid}</ExtLink>
        {p.doi_url && <> · <ExtLink href={p.doi_url}>DOI</ExtLink></>}
        {p.cited_by_sources && <span className="muted"> · cited by {p.cited_by_sources.join(', ')}</span>}
      </div>
      {p.evidence_notes && <p className="small evidence-note">“{p.evidence_notes}”</p>}
    </li>
  )
}

export default function PublicationList({ state, onPage }) {
  const { data, meta, error, loading, reload } = state
  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} what="publications" />
  if (!data?.length) return <EmptyState title="No publications linked" />
  return (
    <>
      <ul className="pub-list">{data.map((p) => <PublicationItem key={p.pmid} p={p} />)}</ul>
      {meta?.pagination && onPage && <Pagination pagination={meta.pagination} onPage={onPage} />}
    </>
  )
}
