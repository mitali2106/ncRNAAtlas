import { Link } from 'react-router-dom'
import { EmptyState, ErrorState, ExtLink, Loading } from './common'

/** Renders the {pathways, genes_without_mapping, notes} payload of inferred-pathway endpoints. */
export default function PathwayList({ state }) {
  const { data, error, loading, reload } = state
  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} what="pathways" />
  if (!data) return null
  return (
    <>
      <p className="small muted">{data.notes}</p>
      {data.gene_count === 0 ? (
        <EmptyState title="No related genes, so no pathways can be inferred" />
      ) : data.pathways.length === 0 ? (
        <EmptyState title="No KEGG mapping available for the related genes" />
      ) : (
        <div className="table-wrap">
          <table className="table compact">
            <thead>
              <tr><th scope="col">Pathway</th><th scope="col">KEGG ID</th><th scope="col">Via genes</th><th scope="col">Mapping</th></tr>
            </thead>
            <tbody>
              {data.pathways.map((p) => (
                <tr key={p.id}>
                  <td><Link to={`/pathways/${p.id}`}>{p.pathway_name || p.pathway_identifier}</Link></td>
                  <td className="mono small"><ExtLink href={p.pathway_url}>{p.pathway_identifier}</ExtLink></td>
                  <td className="small">
                    {p.genes.map((g, i) => (
                      <span key={g.id}>{i > 0 && ', '}<Link to={`/genes/${g.id}`} className="mono">{g.approved_gene_symbol}</Link></span>
                    ))}
                  </td>
                  <td className="small muted">inferred via genes · {p.mapping_source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.genes_without_mapping?.length > 0 && (
        <p className="small muted">
          No pathway mapping: {data.genes_without_mapping.map((g) => `${g.approved_gene_symbol} (${g.reason})`).join('; ')}
        </p>
      )}
    </>
  )
}
