// Human-readable labels for controlled vocabularies (mirrors backend/app/models/constants.py).

export const EVIDENCE_LEVELS = {
  experimental: 'Experimental (source-reported)',
  computational_prediction: 'Computational prediction',
  literature_unclear: 'Literature, validation unclear',
  conflicting: 'Conflicting evidence',
  unverified: 'Unverified',
}

export const VALIDATION_STATUSES = {
  not_reviewed: 'Not reviewed',
  under_review: 'Under review',
  curator_confirmed: 'Curator confirmed',
  insufficient_evidence: 'Insufficient evidence',
  conflicting: 'Conflicting (curator)',
  curator_rejected: 'Curator rejected',
}

export const ASSOCIATION_TYPES = {
  expression: 'Expression',
  circulating_biomarker: 'Circulating biomarker',
  genetic_variant: 'Genetic variant',
  epigenetic: 'Epigenetic',
  functional: 'Functional',
  target_mediated: 'Target-mediated',
  regulatory: 'Regulatory / interaction',
  therapeutic_target: 'Therapeutic target',
  other: 'Other',
}

export const GENE_RELATIONSHIPS = {
  experimentally_validated_target: 'Experimentally validated target',
  inferred_target: 'Inferred target',
  disease_associated_gene: 'Disease-associated gene',
  indirectly_related: 'Indirectly related',
}

export const REVIEW_OUTCOMES = {
  supports_direct_experimental: 'Supports — direct experimental',
  supports_indirect: 'Supports — indirect only',
  prediction_only: 'Prediction only',
  does_not_support: 'Does not support',
  insufficient: 'Insufficient to decide',
  conflicting: 'Contradicts other evidence',
}

export const DIRECTIONS = {
  up: 'Up-regulated',
  down: 'Down-regulated',
  not_significant: 'Not significant',
  mixed: 'Mixed (up and down reported)',
  unspecified: '—',
}

export const label = (map, key) => map[key] || key || '—'

export const formatNumber = (n) => (typeof n === 'number' ? n.toLocaleString() : '—')

export function formatDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

// Categorical series colors (validated reference palette, fixed order): slot 1 = miRNA, slot 2 = lncRNA.
export const RNA_TYPE_COLORS = { miRNA: '#2a78d6', lncRNA: '#eb6834' }
