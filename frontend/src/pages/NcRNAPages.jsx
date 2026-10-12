import { Network } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import AssociationTable from '../components/AssociationTable'
import PathwayList from '../components/PathwayList'
import PublicationList from '../components/PublicationList'
import {
  EmptyState,
  ErrorState,
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
import { GENE_RELATIONSHIPS, label } from '../utils/labels'

export function NcRNAList() {
  const [q, setQ] = useState('')
  const [type, setType] = useState('')
  const [organism, setOrganism] = useState('Homo sapiens')
  const [resolution, setResolution] = useState('')
  const [page, setPage] = useState(1)
  const dq = useDebounce(q, 300)
  const { data, meta, error, loading, reload } = useApi(
    () => api.ncrnas({ q: dq, type, organism, resolution_status: resolution, page, per_page: 25 }),
    [dq, type, organism, resolution, page],
  )
  const reset = (fn) => (e) => {
    fn(e.target.value)
    setPage(1)
  }
  return (
    <>
      <PageHeader eyebrow="Explore" title="ncRNAs">
        <p className="muted">miRNAs are stored at the precursor/locus level (miRBase IDs); lncRNAs by HGNC-approved symbol.</p>
      </PageHeader>
      <div className="filters">
        <input type="search" placeholder="Name, alias or identifier" value={q} onChange={reset(setQ)} aria-label="Search ncRNAs" maxLength={100} />
        <select value={type} onChange={reset(setType)} aria-label="RNA type">
          <option value="">miRNA and lncRNA</option>
          <option value="miRNA">miRNA</option>
          <option value="lncRNA">lncRNA</option>
        </select>
        <select value={organism} onChange={reset(setOrganism)} aria-label="Organism">
          <option value="Homo sapiens">Homo sapiens</option>
          <option value="all">All organisms (non-human labelled)</option>
          <option value="Mus musculus">Mus musculus</option>
          <option value="Rattus norvegicus">Rattus norvegicus</option>
        </select>
        <select value={resolution} onChange={reset(setResolution)} aria-label="Identifier resolution">
          <option value="">Any identifier status</option>
          <option value="resolved">Resolved</option>
          <option value="ambiguous">Ambiguous</option>
          <option value="unresolved">Unresolved</option>
        </select>
      </div>
      {loading && <Loading />}
      <ErrorState error={error} onRetry={reload} what="ncRNAs" />
      {data && data.length === 0 && <EmptyState title="No ncRNAs match these filters" />}
      {data && data.length > 0 && (
        <Section title="ncRNA entities" subtitle="Sorted by number of associations">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Name</th><th scope="col">Type</th><th scope="col">Identifier</th>
                  <th scope="col">Organism</th><th scope="col">Identity</th><th scope="col" className="num">Associations</th>
                </tr>
              </thead>
              <tbody>
                {data.map((n) => (
                  <tr key={n.id}>
                    <td><Link to={`/ncrnas/${n.id}`} className="mono">{n.canonical_name}</Link></td>
                    <td><TypeBadge type={n.ncrna_type} /></td>
                    <td className="mono small">{n.stable_identifier ? <ExtLink href={n.identifier_url}>{n.stable_identifier}</ExtLink> : '—'}</td>
                    <td className="small">{n.organism}</td>
                    <td><ResolutionBadge status={n.resolution_status} /></td>
                    <td className="num">{n.association_count}</td>
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

function Sequence({ seq, source }) {
  if (!seq) return <span className="muted">Not stored (fetch with scripts/normalize_data.py --sequences or import miRBase miRNA.dat)</span>
  const shown = seq.length > 300 ? `${seq.slice(0, 300)}…` : seq
  return (
    <div>
      <code className="sequence">{shown}</code>
      <div className="small muted">{seq.length.toLocaleString()} nt · source: {source}</div>
    </div>
  )
}

function GeneRelationships({ id }) {
  const [page, setPage] = useState(1)
  const { data, meta, error, loading, reload } = useApi(() => api.ncrnaGenes(id, { page, per_page: 25 }), [id, page])
  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} what="gene relationships" />
  return (
    <>
      <h3 className="h3">General ncRNA–gene relationships</h3>
      <p className="small muted">{meta.notes}</p>
      {data.interactions.length === 0 ? (
        <EmptyState title="No ncRNA–gene relationships recorded" />
      ) : (
        <div className="table-wrap">
          <table className="table compact">
            <thead>
              <tr><th scope="col">Gene</th><th scope="col">Relationship</th><th scope="col">Strength</th><th scope="col">Methods</th><th scope="col">Source</th><th scope="col">PMID</th></tr>
            </thead>
            <tbody>
              {data.interactions.map((i) => (
                <tr key={i.id}>
                  <td><Link to={`/genes/${i.gene.id}`} className="mono">{i.gene.approved_gene_symbol}</Link></td>
                  <td><span className={`rel rel-${i.relationship}`}>{label(GENE_RELATIONSHIPS, i.relationship)}</span></td>
                  <td className="small">{i.evidence_strength.replace('_', ' ')}</td>
                  <td className="small">{i.experimental_methods || '—'}</td>
                  <td className="small">{i.source_database}</td>
                  <td>{i.pmid ? <Link to={`/publications/${i.pmid}`}>{i.pmid}</Link> : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pagination pagination={meta.pagination} onPage={setPage} />
      <h3 className="h3">Genes named in disease-specific association records</h3>
      {data.association_gene_links.length === 0 ? (
        <EmptyState title="No association-specific gene links" />
      ) : (
        <ul className="result-list">
          {data.association_gene_links.map((l) => (
            <li key={`${l.association_id}-${l.gene.id}-${l.gene_relationship}`}>
              <Link to={`/genes/${l.gene.id}`} className="mono">{l.gene.approved_gene_symbol}</Link>{' '}
              <span className={`rel rel-${l.gene_relationship}`}>{label(GENE_RELATIONSHIPS, l.gene_relationship)}</span>{' '}
              in <Link to={`/associations/${l.association_id}`}>{l.disease.canonical_name}</Link>
              <span className="muted small"> ({l.source_database}{l.pmid ? `, PMID ${l.pmid}` : ''})</span>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

export function NcRNADetail() {
  const { id } = useParams()
  const { data: n, error, loading, reload } = useApi(() => api.ncrna(id), [id])
  const pathways = useApi(() => api.ncrnaPathways(id), [id])
  const [pubPage, setPubPage] = useState(1)
  const pubs = useApi(() => api.ncrnaPublications(id, { page: pubPage, per_page: 10 }), [id, pubPage])

  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} what="this ncRNA" />
  return (
    <>
      <PageHeader eyebrow={`${n.ncrna_type} · ${n.organism}`} title={<span className="mono">{n.canonical_name}</span>}
        actions={<Link to={`/network?focus_type=ncrna&focus_id=${n.id}`} className="btn"><Network size={16} aria-hidden /> Network</Link>}>
        {n.description && <p className="muted">{n.description}</p>}
      </PageHeader>
      {n.organism !== 'Homo sapiens' && (
        <p className="banner-sample">Non-human record ({n.organism}). It is excluded from human statistics and identifier resolution.</p>
      )}
      <div className="grid-2">
        <Section title="Identity">
          <KeyValue items={[
            ['Canonical name', <span className="mono">{n.canonical_name}</span>],
            ['RNA type', <TypeBadge type={n.ncrna_type} />],
            ['Organism', n.organism],
            ['Stable identifier', n.stable_identifier ? <ExtLink href={n.identifier_url}>{n.identifier_namespace} {n.stable_identifier}</ExtLink> : null],
            ['Identifier resolution', <><ResolutionBadge status={n.resolution_status} note={n.resolution_note} /> {n.resolution_note && <span className="small muted">{n.resolution_note}</span>}</>],
            ['First recorded by', n.source_database],
            ['Sequence', <Sequence seq={n.sequence} source={n.sequence_source} />],
          ]} />
        </Section>
        <Section title="Aliases & cross-references">
          <h3 className="h3">Names</h3>
          {n.aliases.names.length ? (
            <ul className="chips">
              {n.aliases.names.map((a) => (
                <li key={`${a.alias}-${a.source_database}-${a.alias_type}`} title={`${a.alias_type} · ${a.source_database}`}>{a.alias} <span className="muted">· {a.alias_type.replace('_', ' ')}</span></li>
              ))}
            </ul>
          ) : <p className="muted">None recorded</p>}
          <h3 className="h3">Identifiers</h3>
          {n.aliases.identifiers.length ? (
            <ul className="chips">
              {n.aliases.identifiers.map((a) => (
                <li key={`${a.alias}-${a.namespace}`}><ExtLink href={a.url}>{a.namespace}: {a.alias}</ExtLink></li>
              ))}
            </ul>
          ) : <p className="muted">None recorded</p>}
          <KeyValue items={[
            ['Associations', n.counts.associations], ['Diseases', n.counts.diseases],
            ['Gene relationships', n.counts.gene_relationships], ['Publications', n.counts.publications],
          ]} />
        </Section>
      </div>
      <Section title="Associated diseases" subtitle="Each row links to its evidence, sources and publications">
        <AssociationTable fetcher={(p) => api.ncrnaAssociations(id, p)} deps={[id]} hide={['ncrna', 'ncrna_type']}
          emptyText="This ncRNA exists in the database but has no recorded disease associations." />
      </Section>
      <Section title="Associated genes"><GeneRelationships id={id} /></Section>
      <Section title="KEGG pathways (inferred via genes)">
        <PathwayList state={pathways} />
      </Section>
      <Section title="Supporting publications">
        <PublicationList state={pubs} onPage={setPubPage} />
      </Section>
    </>
  )
}
