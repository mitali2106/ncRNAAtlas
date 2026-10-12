import { Download, Focus, RotateCcw, Search, X } from 'lucide-react'
import { useCallback, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import NetworkGraph from '../components/NetworkGraph'
import { EDGE_STYLE, NODE_STYLE, toElements } from '../utils/networkStyle'
import { EmptyState, ErrorState, EvidenceBadge, KeyValue, Loading, PageHeader } from '../components/common'
import { useApi } from '../hooks/useApi'
import { api } from '../services/api'
import { ASSOCIATION_TYPES, EVIDENCE_LEVELS, GENE_RELATIONSHIPS, label } from '../utils/labels'

const EDGE_KINDS = [
  ['ncrna_disease', 'ncRNA–disease associations'],
  ['ncrna_gene', 'ncRNA–gene relationships'],
  ['gene_disease', 'Gene–disease (named in an association record)'],
]
const NODE_PATH = { ncrna: '/ncrnas', disease: '/diseases', gene: '/genes' }

function download(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export default function NetworkPage() {
  const [params, setParams] = useSearchParams()
  const focusType = params.get('focus_type') || ''
  const focusId = params.get('focus_id') || ''
  const [ncrnaType, setNcrnaType] = useState('')
  const [evidence, setEvidence] = useState([])
  const [include, setInclude] = useState(EDGE_KINDS.map(([k]) => k))
  const [maxAssoc, setMaxAssoc] = useState(150)
  const [term, setTerm] = useState('')
  const [matches, setMatches] = useState(null)
  const [selected, setSelected] = useState(null)
  const graphRef = useRef(null)
  const navigate = useNavigate()

  const { data, error, loading, reload } = useApi(
    () => api.network({
      focus_type: focusType || undefined, focus_id: focusId || undefined, ncrna_type: ncrnaType,
      evidence_level: evidence, include, max_associations: maxAssoc,
    }),
    [focusType, focusId, ncrnaType, evidence.join(','), include.join(','), maxAssoc],
    { enabled: include.length > 0 },
  )
  const elements = useMemo(() => (data ? toElements(data) : []), [data])
  const onNode = useCallback((d) => setSelected({ type: 'node', d }), [])
  const onEdge = useCallback((d) => setSelected({ type: 'edge', d }), [])

  const toggle = (list, setList, value) =>
    setList(list.includes(value) ? list.filter((v) => v !== value) : [...list, value])

  const exportPng = async () => {
    const blob = await graphRef.current?.png()
    if (blob) download(blob, 'ncrnaatlas_network.png')
  }
  const exportJson = () => {
    const json = graphRef.current?.json()
    if (json) {
      const payload = { exported_from: 'ncRNAAtlas', filters: { focusType, focusId, ncrnaType, evidence, include }, meta: data.meta, cytoscape: json }
      download(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }), 'ncrnaatlas_network.cyjs.json')
    }
  }

  return (
    <>
      <PageHeader eyebrow="Visualization" title="Interaction network">
        <p className="muted">
          Built only from relationships stored in the database. Genes are connected to a disease only when a source
          record names the gene for that specific ncRNA–disease association.
        </p>
      </PageHeader>
      {focusType && (
        <p className="banner-sample">
          Focused on {focusType} #{focusId}.{' '}
          <button type="button" className="btn btn-small" onClick={() => setParams({})}><X size={14} aria-hidden /> Show global network</button>
        </p>
      )}
      <div className="network-layout">
        <aside className="network-controls card" aria-label="Network controls">
          <form onSubmit={(e) => { e.preventDefault(); setMatches(graphRef.current?.highlight(term) ?? 0) }}>
            <label htmlFor="net-search" className="ctl-label">Find in network</label>
            <div className="inline">
              <input id="net-search" type="search" value={term} onChange={(e) => setTerm(e.target.value)} placeholder="e.g. PTEN" />
              <button type="submit" className="btn btn-small" aria-label="Find"><Search size={14} aria-hidden /></button>
            </div>
            {matches !== null && <p className="small muted" aria-live="polite">{matches} matching node{matches === 1 ? '' : 's'}</p>}
          </form>
          <label htmlFor="net-type" className="ctl-label">ncRNA type</label>
          <select id="net-type" value={ncrnaType} onChange={(e) => setNcrnaType(e.target.value)}>
            <option value="">miRNA and lncRNA</option>
            <option value="miRNA">miRNA only</option>
            <option value="lncRNA">lncRNA only</option>
          </select>
          <fieldset>
            <legend className="ctl-label">Evidence level (associations)</legend>
            {Object.entries(EVIDENCE_LEVELS).map(([k, v]) => (
              <label key={k} className="check">
                <input type="checkbox" checked={evidence.includes(k)} onChange={() => toggle(evidence, setEvidence, k)} /> {v}
              </label>
            ))}
            <p className="small muted">None checked = all levels.</p>
          </fieldset>
          <fieldset>
            <legend className="ctl-label">Relationship types</legend>
            {EDGE_KINDS.map(([k, v]) => (
              <label key={k} className="check">
                <input type="checkbox" checked={include.includes(k)} onChange={() => toggle(include, setInclude, k)} /> {v}
              </label>
            ))}
          </fieldset>
          <label htmlFor="net-max" className="ctl-label">Max associations: {maxAssoc}</label>
          <input id="net-max" type="range" min="10" max="600" step="10" value={maxAssoc} onChange={(e) => setMaxAssoc(Number(e.target.value))} />
          <div className="ctl-buttons">
            <button type="button" className="btn btn-small" onClick={() => graphRef.current?.resetLayout()}><RotateCcw size={14} aria-hidden /> Reset layout</button>
            <button type="button" className="btn btn-small" onClick={() => { graphRef.current?.fit(); graphRef.current?.highlight('') ; setMatches(null) }}><Focus size={14} aria-hidden /> Fit</button>
            <button type="button" className="btn btn-small" onClick={exportPng} disabled={!data}><Download size={14} aria-hidden /> PNG</button>
            <button type="button" className="btn btn-small" onClick={exportJson} disabled={!data}><Download size={14} aria-hidden /> Cytoscape JSON</button>
          </div>
          <div className="net-legend">
            <div className="ctl-label">Legend</div>
            {Object.entries(NODE_STYLE).map(([k, s]) => (
              <div key={k} className="legend-row"><span className={`node-swatch shape-${s.shape}`} style={{ background: s.color }} aria-hidden /> {s.label}</div>
            ))}
            {['experimental', 'literature_unclear', 'conflicting'].map((k) => (
              <div key={k} className="legend-row"><span className="edge-swatch" style={{ borderTopStyle: EDGE_STYLE[k].style, borderTopColor: EDGE_STYLE[k].color }} aria-hidden /> {EDGE_STYLE[k].label}</div>
            ))}
            <div className="legend-row"><span className="edge-swatch" style={{ borderTopColor: '#1a8a7a' }} aria-hidden /> ncRNA–gene</div>
            <div className="legend-row"><span className="edge-swatch" style={{ borderTopStyle: 'dashed', borderTopColor: '#7d6bd1' }} aria-hidden /> Gene–disease (via association)</div>
          </div>
        </aside>
        <div className="network-main">
          {include.length === 0 && <EmptyState title="Select at least one relationship type" />}
          {loading && <Loading text="Building network from database records…" />}
          <ErrorState error={error} onRetry={reload} what="the network" />
          {data && !loading && data.nodes.length === 0 && (
            <EmptyState title="No relationships match these filters">Change the filters or import data.</EmptyState>
          )}
          {data && !loading && data.nodes.length > 0 && (
            <>
              <p className="small muted">
                {data.nodes.length} nodes · {data.edges.length} edges · showing {data.meta.associations_shown} of{' '}
                {data.meta.associations_matching} matching associations (most-cited first)
                {data.meta.truncated && ' — increase “Max associations” to see more'}. Drag nodes, scroll to zoom, click for details.
              </p>
              <NetworkGraph ref={graphRef} elements={elements} onNodeClick={onNode} onEdgeClick={onEdge} />
            </>
          )}
          {selected && (
            <div className="card selection" aria-live="polite">
              <button type="button" className="btn btn-small btn-ghost close" onClick={() => setSelected(null)} aria-label="Close details"><X size={14} /></button>
              {selected.type === 'node' ? (
                <>
                  <h3 className="h3">{selected.d.label}</h3>
                  <KeyValue items={[
                    ['Kind', selected.d.kind === 'ncrna' ? selected.d.ncrna_type : selected.d.kind],
                    ['Connections shown', selected.d.degree],
                  ]} />
                  <div className="inline">
                    <Link className="btn btn-small btn-primary" to={`${NODE_PATH[selected.d.kind]}/${selected.d.entity_id}`}>Open details</Link>
                    <button type="button" className="btn btn-small" onClick={() => navigate(`/network?focus_type=${selected.d.kind}&focus_id=${selected.d.entity_id}`)}>Focus network here</button>
                  </div>
                </>
              ) : selected.d.kind === 'ncrna_disease' ? (
                <>
                  <h3 className="h3">Association evidence</h3>
                  <KeyValue items={[
                    ['Type', label(ASSOCIATION_TYPES, selected.d.association_type)],
                    ['Evidence', <EvidenceBadge level={selected.d.evidence_level} />],
                    ['Publications', selected.d.publication_count],
                    ['Sources', selected.d.source_databases.join(', ')],
                  ]} />
                  <Link className="btn btn-small btn-primary" to={`/associations/${selected.d.association_id}`}>Open evidence &amp; provenance</Link>
                </>
              ) : (
                <>
                  <h3 className="h3">{selected.d.kind === 'ncrna_gene' ? 'ncRNA–gene relationship' : 'Gene linked within an association'}</h3>
                  <KeyValue items={[
                    ['Relationship', label(GENE_RELATIONSHIPS, selected.d.relationship)],
                    ['Sources', selected.d.source_databases.join(', ')],
                    ['PMIDs', selected.d.pmids.length ? selected.d.pmids.map((p, i) => <span key={p}>{i > 0 && ', '}<Link to={`/publications/${p}`}>{p}</Link></span>) : null],
                    ['Methods', selected.d.experimental_methods?.join('; ')],
                    ['Evidence strength', selected.d.evidence_strength?.join(', ')],
                  ]} />
                  {selected.d.association_id && <Link className="btn btn-small btn-primary" to={`/associations/${selected.d.association_id}`}>Open association</Link>}
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  )
}
