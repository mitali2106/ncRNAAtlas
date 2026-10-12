# ncRNAAtlas

**An integrated atlas of non-coding RNA–disease associations.**

ncRNAAtlas brings microRNA (miRNA) and long non-coding RNA (lncRNA) disease associations together with genes,
KEGG pathways and the PubMed literature cited for each claim. It is a full-stack bioinformatics application:
a React frontend, a Flask REST API, a relational database (SQLite or PostgreSQL), and a reproducible
ingestion pipeline with provenance tracking, evidence classification and data-quality reporting.

---

## Contents

1. [Scientific motivation](#1-scientific-motivation)
2. [Problem statement and objectives](#2-problem-statement-and-objectives)
3. [Novelty and contribution](#3-novelty-and-contribution)
4. [Technology stack](#4-technology-stack)
5. [System architecture](#5-system-architecture)
6. [Database schema](#6-database-schema)
7. [Data sources](#7-data-sources)
8. [Data collection, standardization and deduplication](#8-data-collection-standardization-and-deduplication)
9. [Evidence classification and literature review](#9-evidence-classification-and-literature-review)
10. [KEGG pathway mapping](#10-kegg-pathway-mapping)
11. [API](#11-api)
12. [Installation](#12-installation)
13. [Configuration](#13-configuration)
14. [Database initialization](#14-database-initialization)
15. [Sample data (demonstration mode)](#15-sample-data-demonstration-mode)
16. [Real data import](#16-real-data-import)
17. [Running the application](#17-running-the-application)
18. [Testing](#18-testing)
19. [Known limitations](#19-known-limitations)
20. [Future enhancements](#20-future-enhancements)
21. [References and acknowledgements](#21-references-and-acknowledgements)

---

## 1. Scientific motivation

Non-coding RNAs regulate gene expression, and their dysregulation has been reported in cancers,
cardiovascular, neurological and metabolic diseases. Evidence is spread across specialised databases
(HMDD for miRNAs, LncRNADisease for lncRNAs), nomenclature authorities (miRBase, HGNC, RNAcentral), disease
vocabularies (MeSH), pathway resources (KEGG) and the primary literature (PubMed). Each uses different
identifiers, naming conventions and notions of "evidence".

## 2. Problem statement and objectives

Researchers who want to know *"what is known about miR-21 in hepatocellular carcinoma, which genes are
involved, and how strong is the evidence?"* must query several resources, reconcile names by hand, and judge
what each database means by "validated". ncRNAAtlas aims to:

* search ncRNAs, diseases, genes and PMIDs in one place (names, aliases, identifiers);
* show every ncRNA–disease association with its **source records, PMIDs and original data**;
* **distinguish** source-reported experimental evidence, unclear literature support, predictions,
  conflicting evidence and unverified records, and keep these separate from independent curator review;
* connect associations to genes and KEGG pathways without overstating what those links mean;
* visualise ncRNA–gene–disease relationships as an interactive network built only from stored relationships;
* make imports reproducible, auditable and quality-controlled.

## 3. Novelty and contribution

* **Provenance-first integration.** Every association keeps each supporting source record verbatim
  (`original_record`), with source version, import job and per-record evidence classification.
* **Evidence ≠ source ≠ validation.** Three separate fields: what the source reports (evidence level), where it
  came from (sources), and whether ncRNAAtlas curators confirmed it (validation status). Automated keyword
  hints can never confirm an association.
* **Conservative identity resolution.** miRNA loci are resolved through HGNC and miRBase accessions;
  locus-ambiguous names are flagged, not guessed. Diseases resolve to MeSH only on exact descriptor or
  exact *synonym* matches; narrower concepts are not merged into broader ones.
* **Honest network semantics.** Gene–disease edges appear only when a source record names that gene for that
  association. General miRNA targets are stored separately from disease evidence.
* **Real data, documented quirks.** Issues found while ingesting the real files are handled and documented:
  HMDD's mixed text encodings, LncRNADisease's mix of RNA classes and species, and MeSH heading renames.

## 4. Technology stack

| Layer | Technology |
|---|---|
| Frontend | React 19, Vite 6, React Router 6, Recharts 3, Cytoscape.js 3 (small React wrapper), Lucide icons, native Fetch |
| Backend | Python 3.14, Flask 3.1, Flask-CORS, Flask-SQLAlchemy / SQLAlchemy 2.1, Flask-Migrate (Alembic), Requests, Pandas (available for analysis) |
| Database | SQLite (development, default) · PostgreSQL via `DATABASE_URL` (psycopg2) |
| External | NCBI E-utilities, KEGG REST, MeSH lookup + SPARQL, RNAcentral REST, HGNC, HMDD, LncRNADisease |
| Testing | pytest (backend), Vitest + React Testing Library (frontend) |

Biopython was not needed: the only sequence handling is parsing miRBase's EMBL-format `miRNA.dat`, which a
small dedicated parser covers. `react-cytoscapejs` does not declare React 19 support, so a ~100-line wrapper
around Cytoscape.js is used instead.

## 5. System architecture

```mermaid
flowchart LR
    subgraph Browser
      R[React SPA<br/>Dashboard · Search · Explorers · Network · Admin]
    end
    subgraph API[Flask REST API /api]
      RT[routes] --> SV[services<br/>queries · statistics · network · sources]
      RT --> V[validation<br/>evidence · literature review · quality]
      RT --> IN[ingestion<br/>adapters · pipeline · enrichment · runner]
      IN --> NM[normalization<br/>text · miRNA · resolver]
      SV --> M[SQLAlchemy models]
      IN --> M
    end
    R -- JSON --> RT
    M --> DB[(SQLite / PostgreSQL)]
    IN -. rate-limited, cached .-> X[PubMed · KEGG · MeSH · RNAcentral]
    NM --> H[HGNC complete set]
    CLI[scripts/*.py] --> IN
```

The methodology flowchart is in [docs/methodology.md](docs/methodology.md).

## 6. Database schema

The schema has 15 tables. The main ones are `ncrnas`, `diseases`, `genes`, `aliases`, `associations`,
`association_sources`, `publications`, `association_publications`, `association_genes`,
`ncrna_gene_interactions`, `pathways`, `gene_pathways`, `literature_reviews`, `import_jobs` and
`external_cache`. The ER diagram, constraints and deviations from the original specification are in
[docs/database_schema.md](docs/database_schema.md).

```mermaid
erDiagram
    NCRNAS ||--o{ ASSOCIATIONS : ""
    DISEASES ||--o{ ASSOCIATIONS : ""
    ASSOCIATIONS ||--|{ ASSOCIATION_SOURCES : provenance
    ASSOCIATIONS ||--o{ ASSOCIATION_PUBLICATIONS : cites
    PUBLICATIONS ||--o{ ASSOCIATION_PUBLICATIONS : ""
    ASSOCIATIONS ||--o{ ASSOCIATION_GENES : "names gene"
    GENES ||--o{ ASSOCIATION_GENES : ""
    NCRNAS ||--o{ NCRNA_GENE_INTERACTIONS : targets
    GENES ||--o{ NCRNA_GENE_INTERACTIONS : ""
    GENES ||--o{ GENE_PATHWAYS : ""
    PATHWAYS ||--o{ GENE_PATHWAYS : ""
    ASSOCIATIONS ||--o{ LITERATURE_REVIEWS : ""
```

## 7. Data sources

| Resource | Used for | Access |
|---|---|---|
| HMDD v3.2 | miRNA–disease records | Bulk `alldata.txt` |
| LncRNADisease v3.0 | lncRNA–disease records | Bulk `website_alldata.tsv` |
| HGNC | Gene / lncRNA / miRNA-locus nomenclature, NCBI Gene, miRBase and RNAcentral cross-references | Complete set TSV (CC0) |
| miRBase | miRNA sequences and mature products | Local `miRNA.dat` (website unreachable during development) |
| RNAcentral | Sequences | REST API |
| PubMed | Publication metadata, literature search | E-utilities |
| KEGG | Gene → pathway | REST API (academic use) |
| MeSH | Disease identifiers | Lookup API + SPARQL |
| miRTarBase | Optional miRNA targets | Manual download → `mirtarbase` adapter |

What each source is *not* used for, plus the upload schemas: [docs/data_sources.md](docs/data_sources.md).

## 8. Data collection, standardization and deduplication

* **Collection:** `scripts/download_sources.py` fetches the bulk files and records the URL, size, SHA-256 and
  timestamp. It resumes dropped connections, which the HMDD server produces frequently.
* **Adapters:** one per format (`hmdd`, `lncrnadisease`, `generic_associations`, `generic_targets`,
  `mirtarbase`). New sources only need a new adapter.
* **Standardization:**
  * miRNAs are kept at locus level and resolved to miRBase accessions via HGNC;
  * lncRNAs and genes are resolved via HGNC approved, then unique previous, then unique alias symbols;
  * diseases get a MeSH ID only on an exact descriptor or exact synonym match;
  * non-human records are labelled and excluded from human statistics.
* **Deduplication:** an association is keyed by `(ncRNA, disease, association type)`. Merges keep every source
  record and PMID. Re-imports are idempotent. Similar-looking names are never merged.

Details: [docs/methodology.md](docs/methodology.md).

## 9. Evidence classification and literature review

| Evidence level | Assigned when |
|---|---|
| `experimental` | The source reports an experimental category or method **and** a PMID |
| `literature_unclear` | A PMID without a stated method (e.g. HMDD "other") |
| `computational_prediction` | Declared prediction (uploads) |
| `conflicting` | Up- *and* down-regulation reported for the same ncRNA/disease/type |
| `unverified` | No PMID and no method |

The validation status (`not_reviewed` → `under_review` → `curator_confirmed` / `insufficient_evidence` /
`conflicting` / `curator_rejected`) changes **only** when a curator records a review, through the admin UI or
`scripts/validate_associations.py`. `confidence_score` is never computed.

## 10. KEGG pathway mapping

Genes with an HGNC-resolved NCBI Gene ID are linked to KEGG pathways (`link/pathway/hsa:<id>`). These
gene–pathway links are *direct*. Pathways shown for ncRNAs, diseases and associations are *inferred via genes*
and labelled as such. Unmappable genes are listed. If KEGG is unreachable, the cached sample mapping is used,
with its retrieval date.

## 11. API

44 endpoints under `/api`, for example:

```
GET /api/health                 GET /api/statistics            GET /api/sources
GET /api/ncrnas?q=MIR21         GET /api/ncrnas/:id/associations?evidence_level=experimental
GET /api/diseases/:id           GET /api/genes/:id/associations
GET /api/associations?source=HMDD&ncrna_type=miRNA&disease=hepatocellular&sort=publications
GET /api/associations/:id/sources   GET /api/publications/17681183
GET /api/network?focus_type=gene&focus_id=1&include=ncrna_disease,ncrna_gene
GET /api/search?q=pten          GET /api/search/suggest?q=hsa-mir-2
```

Full reference: [docs/api_documentation.md](docs/api_documentation.md).

## 12. Installation

Prerequisites: **Python ≥ 3.11** (developed on 3.14), **Node.js ≥ 18** (developed on 24) and npm. PostgreSQL
is optional.

```bash
git clone <repo> ncRNAAtlas && cd ncRNAAtlas

# Backend
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt

# Frontend
cd frontend && npm install && cd ..
```

## 13. Configuration

```bash
cp .env.example .env     # then edit; never commit .env
```

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | SQLite file `data/ncrnaatlas.db` | e.g. `postgresql+psycopg2://user:pass@localhost:5432/ncrnaatlas` |
| `ADMIN_TOKEN` | *(empty: admin disabled)* | Shared secret for upload/review endpoints |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Allowed browser origins |
| `EXTERNAL_LOOKUPS_ENABLED` | `true` | Set `false` for fully offline operation |
| `NCBI_API_KEY`, `NCBI_EMAIL` | — | Optional NCBI identification (10 req/s with a key) |
| `EXTERNAL_TIMEOUT`, `EXTERNAL_RATE_LIMIT_PER_MINUTE`, `MAX_UPLOAD_MB`, `HGNC_PATH` | 15 s, 30, 25 MB, auto | |

## 14. Database initialization

```bash
python scripts/initialize_database.py              # apply Alembic migrations
python scripts/initialize_database.py --reset      # SQLite only: delete and recreate (asks to confirm)
```

PostgreSQL: create an empty database, set `DATABASE_URL`, then run the same command. Migrations live in
`backend/migrations/`, and `cd backend && flask --app run db upgrade` also works.

## 15. Sample data (demonstration mode)

```bash
python scripts/initialize_database.py --sample     # migrate + import the sample, fully offline
# or, on an existing database:
python scripts/import_data.py sample
```

The sample is an **excerpt of real records**: verbatim HMDD and LncRNADisease rows for 9 miRNAs and 10 lncRNAs
across 16 diseases, plus small hand-curated association and target files in which every claim was checked
against the cited PubMed abstract. It also ships cached HGNC, MeSH, PubMed and KEGG lookups. It contains **no
synthetic records**, and the dashboard shows a "Sample mode" banner because counts describe the excerpt only.
Provenance: `data/sample/manifest.json`.

## 16. Real data import

```bash
python scripts/download_sources.py                 # HMDD, LncRNADisease, HGNC → data/raw/ (+ manifest)
python scripts/import_data.py real                 # HMDD + LncRNADisease + PubMed metadata
python scripts/normalize_data.py --diseases        # retry MeSH for unresolved diseases
python scripts/map_pathways.py                     # KEGG gene → pathway
python scripts/normalize_data.py --sequences       # optional: miRNA sequences from RNAcentral
python scripts/normalize_data.py --report          # data-quality report → data/reports/
```

Optional sources:

```bash
python scripts/import_data.py mirbase    --path miRNA.dat                # sequences + mature-product aliases
python scripts/import_data.py mirtarbase --path hsa_MTI.csv --source-version 10.0
python scripts/import_data.py generic    --path my_curation.tsv --source-version 2026-10
python scripts/import_data.py targets    --path my_targets.tsv
```

Every command accepts `--dry-run`, `--human-only`, `--skip-unresolved`, `--no-live` and `--limit N`. Each
import is logged in `import_jobs` and writes `data/reports/import_job_<id>.json` and `.csv`.

**Literature review:**

```bash
python scripts/validate_associations.py queue
python scripts/validate_associations.py triage --ncrna hsa-mir-21 --disease "Carcinoma, Hepatocellular" --fetch
python scripts/validate_associations.py worksheet --ncrna hsa-mir-21 --out data/reports/review.csv
python scripts/validate_associations.py review --association-id 12 --pmid 17681183 \
       --outcome supports_direct_experimental --evidence-type "direct target (luciferase)" --reviewer "Your Name"
python scripts/validate_associations.py import-worksheet --path data/reports/review.csv
```

## 17. Running the application

Run each in its own terminal from the project root:

```bash
# Backend API on http://127.0.0.1:5000
python backend/run.py

# Frontend on http://localhost:5173 (proxies /api to the backend)
cd frontend && npm run dev
```

Production: `cd frontend && npm run build` produces static files in `frontend/dist/`. Serve them behind any web
server that proxies `/api` to the Flask app (for example run with `gunicorn "app:create_app()"` from `backend/`
on Linux), with `APP_ENV=production`, a PostgreSQL `DATABASE_URL`, a strong `SECRET_KEY` and restricted
`CORS_ORIGINS`.

## 18. Testing

```bash
cd backend && python -m pytest -q          # 106 tests
cd frontend && npm test                    # 16 tests
cd frontend && npx eslint src && npm run build
```

External services are mocked in all tests. Backend fixtures are excerpts of the real HMDD, LncRNADisease
and HGNC files and real PubMed/KEGG responses.

| Area | Covered |
|---|---|
| Database | Entity creation, FK enforcement, uniqueness, check constraints, association↔publication, gene↔pathway, cascades |
| Processing | miRNA parsing, alias/previous-symbol resolution, ambiguous loci, disease exact/synonym matching, gene IDs, organism handling, evidence rules, conflict detection, missing fields, malformed PMIDs, in-file duplicates, idempotent re-import, dry runs, synonym-disease merge |
| Backend | Search and suggest, every entity endpoint, filters combined, pagination, stable sort, 400/404/409/429/503, external failure and fallback, admin auth, upload validation, preview → commit → report, curator review |
| Frontend | Search autocomplete and empty results, filter behaviour and clearing, detail page, not-found, empty and onboarding states, error states, network filtering |

## 19. Known limitations

* Evidence levels inherit the coverage and curation of HMDD and LncRNADisease; membership in a database is
  not independent validation, and no association in the shipped data is curator-confirmed.
* HMDD records many miRNAs without a locus (e.g. `hsa-mir-16`); these remain flagged as *ambiguous*.
  Precursor-level storage loses 5p/3p arm information.
* Many LncRNADisease lncRNA names are not HGNC symbols (LOC…, NONHSAT…, TCONS…, Ensembl transcript IDs) and
  remain unresolved.
* Disease names that are neither MeSH descriptors nor exact MeSH synonyms (including MeSH narrower concepts)
  remain unresolved; no DO/MONDO cross-mapping is performed.
* No bulk miRNA–target resource is imported automatically (miRTarBase requires a manual download), so gene and
  pathway coverage depends on curated or uploaded target data.
* miRBase was unreachable during development; accessions come from HGNC and sequences from RNAcentral or a
  user-supplied `miRNA.dat`.
* PubMed metadata and KEGG mappings reflect their retrieval date.
* The admin interface uses a single shared token, not per-user accounts.
* Tested on SQLite; the PostgreSQL path (same migrations and ORM) was not exercised against a live server.

## 20. Future enhancements

* Disease ontology cross-mapping (MONDO/DO) with explicit mapping provenance.
* Arm-level (mature miRNA) associations when sources provide them.
* Scheduled re-imports with diff reports between source versions.
* Multi-user curator accounts with review audit trails and inter-curator agreement.
* A documented, reproducible evidence-scoring method (only then populating `confidence_score`).
* Enrichment analysis of target genes against KEGG with multiple-testing correction.

## 21. References and acknowledgements

PMIDs below were checked against PubMed.

* Huang Z, et al. HMDD v3.0: a database for experimentally supported human microRNA–disease associations.
  *Nucleic Acids Res.* 2019;47(D1):D1013–D1017. PMID 30364956.
* Cui C, et al. HMDD v4.0: a database for experimentally supported human microRNA–disease associations.
  *Nucleic Acids Res.* 2024;52(D1):D1327–D1332. PMID 37650649.
* Lin X, et al. LncRNADisease v3.0: an updated database of long non-coding RNA-associated diseases.
  *Nucleic Acids Res.* 2024;52(D1):D1365–D1369. PMID 37819033.
* Seal RL, et al. Genenames.org: the HGNC resources in 2023. *Nucleic Acids Res.* 2023;51(D1):D1003–D1009. PMID 36243972.
* Kozomara A, Birgaoanu M, Griffiths-Jones S. miRBase: from microRNA sequences to function.
  *Nucleic Acids Res.* 2019;47(D1):D155–D162. PMID 30423142.
* RNAcentral Consortium. RNAcentral 2021: secondary structure integration, improved sequence search and new
  member databases. *Nucleic Acids Res.* 2021;49(D1):D212–D220. PMID 33106848.
* Kanehisa M, et al. KEGG: biological systems database as a model of the real world.
  *Nucleic Acids Res.* 2025;53(D1):D672–D677. PMID 39417505.
* Sayers EW, et al. Database resources of the National Center for Biotechnology Information.
  *Nucleic Acids Res.* 2024;52(D1):D33–D43. PMID 37994677.
* Cui S, et al. miRTarBase 2025: updates to the collection of experimentally validated microRNA–target
  interactions. *Nucleic Acids Res.* 2025;53(D1):D147–D156. PMID 39578692.
* National Library of Medicine. Medical Subject Headings (MeSH).

Data remain the property of their providers. Respect each resource's licence and terms of use (HGNC and
RNAcentral: CC0; KEGG: academic use of the REST API; HMDD, LncRNADisease and miRTarBase: see their websites)
and cite the original resources when using data obtained through ncRNAAtlas.
