import cytoscape from 'cytoscape'
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'

// Minimal React integration for Cytoscape.js (react-cytoscapejs does not declare
// React 19 support). The graph is rebuilt whenever `elements` change.

const STYLESHEET = [
  {
    selector: 'node',
    style: {
      label: 'data(label)',
      'font-size': 10,
      color: '#1d2733',
      'text-valign': 'bottom',
      'text-margin-y': 3,
      'text-outline-color': '#ffffff',
      'text-outline-width': 2,
      'background-color': 'data(color)',
      shape: 'data(shape)',
      width: 'mapData(degree, 1, 20, 16, 40)',
      height: 'mapData(degree, 1, 20, 16, 40)',
      'border-width': 2,
      'border-color': '#ffffff',
    },
  },
  {
    selector: 'edge',
    style: {
      width: 1.6,
      'line-color': 'data(color)',
      'line-style': 'data(lineStyle)',
      'curve-style': 'bezier',
      opacity: 0.8,
    },
  },
  { selector: 'edge[kind = "ncrna_gene"]', style: { 'line-color': '#1a8a7a', 'line-style': 'solid', opacity: 0.6 } },
  { selector: 'edge[kind = "gene_disease"]', style: { 'line-color': '#7d6bd1', 'line-style': 'dashed', opacity: 0.7 } },
  { selector: '.faded', style: { opacity: 0.12, 'text-opacity': 0.2 } },
  { selector: '.match', style: { 'border-color': '#f5b800', 'border-width': 4 } },
  { selector: ':selected', style: { 'border-color': '#f5b800', 'border-width': 4, 'line-color': '#f5b800' } },
]

const LAYOUT = { name: 'cose', animate: false, nodeRepulsion: 9000, idealEdgeLength: 70, padding: 24, randomize: true }

const NetworkGraph = forwardRef(function NetworkGraph({ elements, onNodeClick, onEdgeClick }, ref) {
  const container = useRef(null)
  const cyRef = useRef(null)
  const [tip, setTip] = useState(null)

  useImperativeHandle(ref, () => ({
    resetLayout: () => cyRef.current?.layout(LAYOUT).run(),
    fit: () => cyRef.current?.fit(undefined, 24),
    png: () => cyRef.current?.png({ full: true, scale: 2, bg: '#ffffff', output: 'blob' }),
    json: () => cyRef.current?.json(),
    highlight: (term) => {
      const cy = cyRef.current
      if (!cy) return 0
      cy.elements().removeClass('faded match')
      const t = term.trim().toLowerCase()
      if (!t) return 0
      const hits = cy.nodes().filter((n) => n.data('label').toLowerCase().includes(t))
      if (hits.length) {
        cy.elements().addClass('faded')
        hits.closedNeighborhood().removeClass('faded')
        hits.addClass('match')
        cy.animate({ fit: { eles: hits.closedNeighborhood(), padding: 40 } }, { duration: 300 })
      }
      return hits.length
    },
  }))

  useEffect(() => {
    if (!container.current) return undefined
    const cy = cytoscape({
      container: container.current,
      elements,
      style: STYLESHEET,
      layout: LAYOUT,
      minZoom: 0.15,
      maxZoom: 4,
      wheelSensitivity: 0.25,
    })
    cyRef.current = cy
    const show = (evt, text) => {
      const p = evt.renderedPosition || evt.target.renderedMidpoint?.() || { x: 0, y: 0 }
      setTip({ x: p.x, y: p.y, text })
    }
    cy.on('mouseover', 'node', (evt) => {
      const d = evt.target.data()
      const kind = d.kind === 'ncrna' ? d.ncrna_type : d.kind
      show(evt, `${d.label} · ${kind} · ${d.degree} connection${d.degree === 1 ? '' : 's'}`)
    })
    cy.on('mouseover', 'edge', (evt) => {
      const d = evt.target.data()
      const text =
        d.kind === 'ncrna_disease'
          ? `Association · ${d.association_type} · ${d.evidence_level} · ${d.publication_count} PMID(s) · ${d.source_databases.join(', ')}`
          : `${d.kind === 'ncrna_gene' ? 'ncRNA–gene' : 'Gene–disease (via association)'} · ${d.relationship} · ${d.source_databases.join(', ')}`
      show(evt, text)
    })
    cy.on('mouseout', 'node, edge', () => setTip(null))
    cy.on('tap', 'node', (evt) => onNodeClick?.(evt.target.data()))
    cy.on('tap', 'edge', (evt) => onEdgeClick?.(evt.target.data()))
    cy.on('pan zoom', () => setTip(null))
    return () => {
      cy.destroy()
      cyRef.current = null
    }
  }, [elements, onNodeClick, onEdgeClick])

  return (
    <div className="network-canvas-wrap">
      <div ref={container} className="network-canvas" data-testid="network-canvas" />
      {tip && (
        <div className="network-tip" style={{ left: tip.x + 12, top: tip.y + 12 }} role="tooltip">
          {tip.text}
        </div>
      )}
    </div>
  )
})

export default NetworkGraph
