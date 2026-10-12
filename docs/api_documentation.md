# REST API

Base URL: `http://127.0.0.1:5000/api`. In development the frontend reaches it through the Vite proxy at `/api`.

## Conventions

* **Success:** `{"data": ..., "pagination"?: {...}, "filters"?: {...}, "notes"?: "..."}`
* **Error:** `{"error": {"status": 404, "code": "not_found", "message": "...", "details"?: {...}}}`
* **Pagination:** `page` (≥1), `per_page` (1–100, default 25). Responses include
  `pagination = {page, per_page, total, pages}`.
* **Sorting is stable:** every sort adds the primary key as a tiebreaker.
* **Validation:** invalid integers, unknown vocabulary values, unknown sort keys and over-long queries
  (>100 characters) return `400`.
* **Organism:** list endpoints default to `organism=Homo sapiens`. Pass `organism=all` to include non-human
  records, which are labelled in every response.

| Status | `code` | Meaning |
|---|---|---|
| 400 | `bad_request` | Invalid parameter |
| 401 | `unauthorized` | Missing or invalid `X-Admin-Token` |
| 403 | `admin_disabled` | `ADMIN_TOKEN` not configured on the server |
| 404 | `not_found` | Record does not exist |
| 409 | `conflict` | Upload already imported |
| 413 | `payload_too_large` | Upload exceeds `MAX_UPLOAD_MB` |
| 429 | `rate_limited` | Too many externally dependent requests |
| 503 | `external_unavailable` / `external_disabled` | PubMed/KEGG unavailable or disabled; stored data unaffected |

## Health and metadata

| Method & path | Description |
|---|---|
| `GET /health` | Database connectivity, dialect, whether external lookups and admin are enabled |
| `GET /statistics` | Live dataset statistics (totals, distributions, top diseases/ncRNAs, recent imports). Synthetic records excluded. |
| `GET /sources` | Source registry with purpose, limitations, citation, licence, record counts and last import |
| `GET /vocabularies` | Controlled vocabularies (evidence levels, statuses, association types, gene relationships, review outcomes) |
| `GET /import-jobs` | Paginated import audit log (`status` filter) |
| `GET /import-jobs/:id` | One import job (used to poll progress) |

## ncRNAs

| Method & path | Parameters |
|---|---|
| `GET /ncrnas` | `q` (name, alias or identifier, partial and case-insensitive), `type`/`ncrna_type`, `organism`, `resolution_status`, `sort` = `associations`\|`name`\|`id`\|`type`, `order` |
| `GET /ncrnas/:id` | Identity, sequence, aliases, cross-references, counts |
| `GET /ncrnas/:id/associations` | All association filters (below) |
| `GET /ncrnas/:id/genes` | `{interactions, association_gene_links}`; `relationship` filter |
| `GET /ncrnas/:id/pathways` | Pathways inferred via related genes, plus genes without a mapping |
| `GET /ncrnas/:id/publications` | Paginated publications |

## Diseases

| Method & path | Parameters |
|---|---|
| `GET /diseases` | `q` (name, synonym, MeSH ID), `resolution_status`, `sort` |
| `GET /diseases/:id` | Identity and counts (miRNAs, lncRNAs, publications, evidence levels) |
| `GET /diseases/:id/associations` | All association filters |
| `GET /diseases/:id/genes` | Genes named by source records for this disease's associations |
| `GET /diseases/:id/pathways` | Pathways inferred via those genes |
| `GET /diseases/:id/publications` | Paginated publications |

## Genes

| Method & path | Notes |
|---|---|
| `GET /genes` | `q` matches symbol, alias, previous symbol, name and NCBI Gene ID |
| `GET /genes/:id` | Identity and general ncRNA relationships |
| `GET /genes/:id/associations` | `{direct, via_ncrna_relationships}`: `direct` means a source record names this gene for that association; `via_ncrna_relationships` is an indirect connection only |
| `GET /genes/:id/pathways` | Direct KEGG mappings; `mapping_status` is `mapped`, `no_mapping_available` or `not_mappable` |

## Associations

`GET /associations` filters, which can be combined:

| Parameter | Values |
|---|---|
| `ncrna_type` | `miRNA`, `lncRNA` (comma-separated list allowed) |
| `evidence_level` | `experimental`, `computational_prediction`, `literature_unclear`, `conflicting`, `unverified` |
| `validation_status` | `not_reviewed`, `under_review`, `curator_confirmed`, `insufficient_evidence`, `conflicting`, `curator_rejected` |
| `association_type` | `expression`, `circulating_biomarker`, `genetic_variant`, `epigenetic`, `functional`, `target_mediated`, `regulatory`, `therapeutic_target`, `other` |
| `source` | Source database name (e.g. `HMDD`) |
| `ncrna_id`, `disease_id` | Integer IDs |
| `disease` | Partial disease name |
| `gene_id` / `gene` | Gene named in the association record (ID or exact symbol) |
| `target_gene_id` | Associations of ncRNAs with a stored relationship to this gene |
| `q` | Partial ncRNA or disease name |
| `year_from`, `year_to` | Year of a linked publication |
| `organism` | Default `Homo sapiens`; `all` |
| `sort` | `publications` (default), `ncrna`, `disease`, `evidence`, `type`, `id`; `order` = `asc`\|`desc` |

| Method & path | Description |
|---|---|
| `GET /associations/:id` | Full detail: entities, evidence classification, genes, inferred pathways, reviews |
| `GET /associations/:id/publications` | Publications with the citing sources and evidence notes |
| `GET /associations/:id/sources` | Every source record, including `original_record` exactly as imported |
| `GET /associations/:id/reviews` | Curator reviews and triage hints, plus `validation_status` |

## Literature

| Method & path | Description |
|---|---|
| `GET /publications/:pmid` | Stored record, fetched from PubMed and cached if missing or pending. When PubMed is unavailable, the stored record is returned with `external_note`. Rate-limited. |
| `GET /literature/search?q=&limit=&offset=` | PubMed search through E-utilities. Results are bibliographic hits only. Rate-limited. |

## Pathways and network

| Method & path | Description |
|---|---|
| `GET /pathways` | Pathways containing at least one atlas gene; `q` |
| `GET /pathways/:id` | Member genes, related ncRNAs (via genes) and related associations (via association genes) |
| `GET /network` | Graph JSON. `focus_type` (`ncrna`\|`disease`\|`gene`) + `focus_id`, `ncrna_type`, `evidence_level` (list), `include` (list of `ncrna_disease`, `ncrna_gene`, `gene_disease`), `max_associations` (1–600, default 150), `organism` |

Network response: `{nodes: [{id, kind, entity_id, label, ncrna_type?, degree}], edges: [{id, source, target, kind, ...evidence}], meta: {associations_matching, associations_shown, truncated, edge_policy}}`.

## Search

| Method & path | Description |
|---|---|
| `GET /search?q=&types=&limit=` | Categorized results: `ncrnas`, `diseases`, `genes`, `publications` (PMID or title), `pathways`. Exact matches rank first, then prefix matches. |
| `GET /search/suggest?q=` | Autocomplete from database records (≥2 characters) |

## Admin (header `X-Admin-Token`)

| Method & path | Description |
|---|---|
| `POST /admin/verify` | Check the token |
| `GET /admin/adapters` | Supported formats and their required/optional columns |
| `POST /admin/uploads` | multipart: `file` (.csv/.tsv/.txt, UTF-8), `adapter`, optional `source_version`, `source_database`. Runs a dry-run import and returns a preview with warnings, unresolved names, duplicates and the first 50 records. Nothing is written. |
| `GET /admin/uploads/:upload_id` | Stored preview |
| `POST /admin/uploads/:upload_id/commit` | JSON `{overrides: {ncrna\|disease\|gene: {raw: canonical}}, skip_unresolved, human_only, dataset_label}`. Starts the import (202) and returns the job to poll. |
| `GET /admin/import-jobs/:id/report?format=json\|csv` | Download the job's data-quality report |
| `GET /admin/quality-report?format=json\|csv` | Fresh database-wide quality report |
| `GET /admin/review-queue` | Associations awaiting curator review |
| `POST /admin/associations/:id/triage` | Automated triage hints (`{fetch_metadata: true}` fetches PubMed first). Never confirms an association. |
| `POST /admin/associations/:id/reviews` | `{outcome, pmid?, evidence_type?, notes?, reviewer}`: records a curator decision and recomputes `validation_status` |

No endpoint deletes data.
