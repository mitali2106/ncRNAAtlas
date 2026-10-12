# Database schema

The schema is defined with SQLAlchemy models in `backend/app/models/` and created through the Alembic
migration in `backend/migrations/versions/`. The same migration runs on SQLite (development) and PostgreSQL
(deployment); constraint names follow a fixed naming convention so migrations stay portable.

## Entity-relationship diagram

```mermaid
erDiagram
    NCRNAS ||--o{ ASSOCIATIONS : "has"
    DISEASES ||--o{ ASSOCIATIONS : "has"
    ASSOCIATIONS ||--|{ ASSOCIATION_SOURCES : "provenance"
    ASSOCIATIONS ||--o{ ASSOCIATION_PUBLICATIONS : "cites"
    PUBLICATIONS ||--o{ ASSOCIATION_PUBLICATIONS : "cited by"
    ASSOCIATIONS ||--o{ ASSOCIATION_GENES : "names gene"
    GENES ||--o{ ASSOCIATION_GENES : ""
    NCRNAS ||--o{ NCRNA_GENE_INTERACTIONS : "relates to"
    GENES ||--o{ NCRNA_GENE_INTERACTIONS : ""
    GENES ||--o{ GENE_PATHWAYS : "member of"
    PATHWAYS ||--o{ GENE_PATHWAYS : ""
    ASSOCIATIONS ||--o{ LITERATURE_REVIEWS : "reviewed in"
    IMPORT_JOBS ||--o{ ASSOCIATION_SOURCES : "imported"
    ALIASES }o--|| NCRNAS : "entity_type=ncrna"
    ALIASES }o--|| DISEASES : "entity_type=disease"
    ALIASES }o--|| GENES : "entity_type=gene"

    NCRNAS {
        int id PK
        string canonical_name "unique with organism"
        string stable_identifier "miRBase MI / HGNC ID"
        string identifier_namespace
        string ncrna_type "miRNA | lncRNA (CHECK)"
        string organism
        text sequence
        string resolution_status
        bool is_synthetic
    }
    DISEASES {
        int id PK
        string canonical_name
        string normalized_name UK
        string disease_identifier "MeSH UI"
        string identifier_namespace
        string resolution_status
    }
    GENES {
        int id PK
        string approved_gene_symbol "unique with organism"
        string stable_gene_identifier "NCBI Gene ID"
        string hgnc_id
        string organism
    }
    ASSOCIATIONS {
        int id PK
        int ncrna_id FK
        int disease_id FK
        string association_type "unique with ncrna+disease"
        string regulation_direction
        string evidence_level
        string validation_status
        float confidence_score "never auto-filled"
        datetime last_verified_at
    }
    ASSOCIATION_SOURCES {
        int id PK
        int association_id FK
        string source_database
        string source_record_id "unique per association+source"
        string source_version
        datetime import_timestamp
        int import_job_id FK
        string evidence_level "per record"
        json original_record
    }
    PUBLICATIONS {
        int id PK
        string pmid UK
        string doi
        text publication_title
        int publication_year
        string metadata_status
    }
    ASSOCIATION_PUBLICATIONS {
        int id PK
        int association_id FK
        int publication_id FK "unique pair"
        string source_databases
        text evidence_notes
    }
    ASSOCIATION_GENES {
        int id PK
        int association_id FK
        int gene_id FK
        string gene_relationship "CHECK vocabulary"
        string source_database
        string pmid
    }
    NCRNA_GENE_INTERACTIONS {
        int id PK
        int ncrna_id FK
        int gene_id FK
        string relationship
        string evidence_strength
        string source_database
        string pmid
    }
    PATHWAYS {
        int id PK
        string pathway_identifier "unique with database"
        string pathway_name
        string pathway_database
    }
    GENE_PATHWAYS {
        int gene_id PK
        int pathway_id PK
        string mapping_source
        string mapping_type "direct"
        datetime mapping_timestamp
    }
    ALIASES {
        int id PK
        string entity_type
        int entity_id
        string alias
        string alias_type
        string namespace
        string source_database
    }
    LITERATURE_REVIEWS {
        int id PK
        int association_id FK
        string pmid
        string review_type "curator | automated_triage"
        string outcome
        string reviewer
        datetime reviewed_at
    }
    IMPORT_JOBS {
        int id PK
        string source_database
        string dataset_label "real | sample | synthetic"
        string status
        int records_processed
        int records_inserted
        int records_updated
        int records_skipped
        text error_summary
    }
```

`external_cache` (namespace, cache_key, JSON value) stores MeSH lookups and is not shown.

## Tables

| Table | Purpose | Key constraints |
|---|---|---|
| `ncrnas` | One row per miRNA locus or lncRNA per organism | `UNIQUE(canonical_name, organism)`, `CHECK ncrna_type IN ('miRNA','lncRNA')` |
| `diseases` | Disease concepts as named by sources | `UNIQUE(normalized_name)`; MeSH UI when exactly resolvable |
| `genes` | Genes, normalized to HGNC | `UNIQUE(approved_gene_symbol, organism)` |
| `aliases` | Synonyms, previous symbols, source spellings, cross-reference IDs | `UNIQUE(entity_type, entity_id, alias, source_database)` |
| `associations` | ncRNA–disease relationship of one type | `UNIQUE(ncrna_id, disease_id, association_type)` |
| `association_sources` | One row per supporting source record (provenance) | `UNIQUE(association_id, source_database, source_record_id)` |
| `publications` | PubMed metadata, once per PMID | `UNIQUE(pmid)` |
| `association_publications` | Association ↔ publication links | `UNIQUE(association_id, publication_id)` |
| `association_genes` | Genes named by a source record for a specific association | `UNIQUE(association_id, gene_id, gene_relationship, source_database)`, CHECK on relationship |
| `ncrna_gene_interactions` | General (not disease-specific) ncRNA→gene relationships | `UNIQUE(ncrna_id, gene_id, relationship, source_database, pmid)` |
| `pathways` | KEGG pathways | `UNIQUE(pathway_database, pathway_identifier)` |
| `gene_pathways` | Direct gene→pathway membership from KEGG | composite PK `(gene_id, pathway_id)` |
| `literature_reviews` | Curator decisions and automated triage hints | FK to association |
| `import_jobs` | Audit trail of every import | — |

Foreign keys cascade on delete from entity to association to provenance. In SQLite, `PRAGMA foreign_keys=ON`
is set on every connection, so the constraints are enforced there as well.

## Design notes and deviations from the original specification

* **Publications are normalized.** The specification put bibliographic fields on `association_publications`.
  Here they live once in `publications`, and `association_publications` is the link table. This prevents
  duplicate publication records and lets one PMID support many associations.
* **`ncrna_gene_interactions` was added.** General miRNA targets (for example from miRTarBase) are not
  disease-specific. Storing them in `association_genes` would present them as disease evidence, so they are
  kept separate.
* **Per-record evidence.** `association_sources` stores the evidence level and regulation direction of each
  source record. The association-level values are derived from these records and can be recomputed at any time.
* **`is_synthetic`** flags exist on entities and associations so that synthetic demonstration data can never be
  mixed silently into statistics. The shipped sample dataset contains no synthetic records.
