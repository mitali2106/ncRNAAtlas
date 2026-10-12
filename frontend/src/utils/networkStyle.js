// Node/edge encodings for the interaction network (shared by the graph and its legend).

export const NODE_STYLE = {
  miRNA: { color: '#2a78d6', shape: 'ellipse', label: 'miRNA' },
  lncRNA: { color: '#eb6834', shape: 'ellipse', label: 'lncRNA' },
  disease: { color: '#12355b', shape: 'diamond', label: 'Disease' },
  gene: { color: '#1a8a7a', shape: 'round-rectangle', label: 'Gene' },
}

export const EDGE_STYLE = {
  experimental: { style: 'solid', color: '#4b5768', label: 'Experimental (source-reported)' },
  literature_unclear: { style: 'dashed', color: '#8a94a3', label: 'Literature, validation unclear' },
  computational_prediction: { style: 'dashed', color: '#8a94a3', label: 'Computational prediction' },
  conflicting: { style: 'dotted', color: '#c0392b', label: 'Conflicting evidence' },
  unverified: { style: 'dotted', color: '#a0a8b4', label: 'Unverified' },
}

export function toElements(graph) {
  const nodes = graph.nodes.map((n) => {
    const s = n.kind === 'ncrna' ? NODE_STYLE[n.ncrna_type] || NODE_STYLE.miRNA : NODE_STYLE[n.kind]
    return { data: { ...n, color: s.color, shape: s.shape } }
  })
  const edges = graph.edges.map((e) => {
    const s = EDGE_STYLE[e.evidence_level] || EDGE_STYLE.experimental
    return { data: { ...e, color: s.color, lineStyle: s.style } }
  })
  return [...nodes, ...edges]
}

