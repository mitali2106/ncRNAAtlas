// Response fixtures shaped like the real API. Values mirror the curated sample
// (hsa-mir-21 / PTEN / hepatocellular carcinoma, PMID 17681183).

export const association = {
  id: 7,
  ncrna: { id: 1, canonical_name: 'hsa-mir-21', ncrna_type: 'miRNA', organism: 'Homo sapiens' },
  disease: { id: 3, canonical_name: 'Carcinoma, Hepatocellular', disease_identifier: 'D006528' },
  association_type: 'target_mediated',
  regulation_direction: 'unspecified',
  evidence_level: 'experimental',
  validation_status: 'not_reviewed',
  confidence_score: null,
  publication_count: 3,
  source_record_count: 2,
  source_databases: ['HMDD', 'ncRNAAtlas curated sample'],
  is_synthetic: false,
}

export const page = (data, extra = {}) => ({
  data,
  pagination: { page: 1, per_page: 20, total: data.length, pages: data.length ? 1 : 0 },
  ...extra,
})

export const statistics = (overrides = {}) => ({
  data: {
    totals: {
      ncrnas: 18, associations: 120, human_associations: 115, diseases: 16, genes: 8,
      ncrna_gene_interactions: 9, publications: 140, publications_with_metadata: 140,
      mapped_pathways: 30, genes_with_pathway_mapping: 8,
    },
    is_empty: false,
    dataset_labels: ['sample'],
    ncrna_type_distribution: { miRNA: 9, lncRNA: 9 },
    associations_by_ncrna_type: { miRNA: 70, lncRNA: 50 },
    evidence_level_distribution: { experimental: 100, literature_unclear: 15, conflicting: 5 },
    validation_status_distribution: { not_reviewed: 120 },
    association_type_distribution: { expression: 60, other: 60 },
    organism_distribution: { 'Homo sapiens': 115, 'Mus musculus': 5 },
    source_distribution: { HMDD: 70 },
    top_diseases: [{ id: 3, canonical_name: 'Carcinoma, Hepatocellular', association_count: 20 }],
    top_ncrnas: [{ id: 1, canonical_name: 'hsa-mir-21', ncrna_type: 'miRNA', association_count: 15 }],
    recent_imports: [],
    synthetic_records_excluded: { associations: 0, ncrnas: 0 },
    ...overrides,
  },
})
