# Data sources and import formats

Each resource is listed with what it contributes and what it is *not* used for. Access methods are the ones
verified during development (October 2026). Check each provider's current terms before redistributing data.

| Resource | Role | Access | Not used for |
|---|---|---|---|
| **HMDD v3.2** (http://www.cuilab.cn/hmdd) | miRNA–disease records (category, precursor name, disease, PMID, evidence sentence) | `alldata.txt` bulk download | HMDD membership alone is not independent validation; categories map to evidence levels by documented rules |
| **LncRNADisease v3.0** (http://www.rnanut.net/lncrnadisease/) | lncRNA–disease records (species, dysfunction pattern, validation method, description, causality, PMID) | `website_alldata.tsv` bulk download | circRNA rows (skipped and counted) |
| **HGNC** (https://www.genenames.org) | Approved symbols, previous symbols and aliases for genes, lncRNAs and miRNA loci; links to NCBI Gene, miRBase and RNAcentral | `hgnc_complete_set.txt` (CC0) | Associations |
| **miRBase** (https://www.mirbase.org) | miRNA nomenclature and sequences | Local `miRNA.dat` file (`import_data.py mirbase`) | Disease evidence. The site was unreachable during development, so precursor accessions come from HGNC. |
| **RNAcentral** (https://rnacentral.org) | URS identifiers and sequences | REST API `/api/v1/rna/{URS}` | Disease evidence |
| **PubMed / E-utilities** | Title, authors, journal, year, abstract and DOI for cited PMIDs; literature search | `efetch`, `esearch`, `esummary` (≤3 req/s; ≤10 req/s with `NCBI_API_KEY`) | Co-occurrence is never treated as an association |
| **KEGG REST** (https://rest.kegg.jp) | Human gene → pathway membership; pathway names | `link/pathway/hsa:<entrez>`, `list/pathway/hsa` (academic use) | KEGG does not establish ncRNA–disease associations |
| **MeSH** (https://id.nlm.nih.gov/mesh/) | Disease descriptor IDs | Lookup API, exact label match only | No fuzzy matching |
| **miRTarBase** (https://mirtarbase.cuhk.edu.cn) | Optional miRNA–target interactions | Manual download (the site requires a browser); `mirtarbase` adapter | Target relationships are not disease-specific and are stored separately |

Citations, with PubMed-verified PMIDs, are listed in the README and returned by `GET /api/sources`.

## Observed data characteristics

* **HMDD `alldata.txt` is not uniformly UTF-8.** 1,391 of 35,548 lines contain GBK-encoded characters (for
  example Greek letters). The HMDD adapter decodes each line with the fallbacks `utf-8 → gb18030 → cp1252 →
  latin-1` and reports how many lines needed a fallback in every import report.
* **HMDD reports miRNAs at precursor level**, sometimes without a locus suffix (`hsa-mir-16` rather than
  `hsa-mir-16-1`). Such names are imported but flagged *ambiguous*.
* **The LncRNADisease file mixes lncRNA (12,534) and circRNA (12,905) rows** and four species. All lncRNA rows
  carry a PMID and a validation method.
* **HGNC's complete set** records each miRNA locus's miRBase precursor ID as an alias symbol (`hsa-mir-21`),
  its miRBase accession (`MI0000077`) and an RNAcentral URS. ncRNAAtlas uses these to resolve miRNA identity
  without the miRBase website.

## Generic association upload schema (`generic_associations`)

UTF-8 TSV (or CSV with a `.csv` extension). One row per source record.

| Column | Required | Description |
|---|---|---|
| `ncrna_name` | ✔ | miRBase-style miRNA name (`hsa-mir-21`, `hsa-miR-21-5p`) or lncRNA symbol |
| `ncrna_type` | ✔ | `miRNA` or `lncRNA` (other classes are skipped) |
| `disease_name` | ✔ | Disease name, ideally a MeSH descriptor heading |
| `source_database` | ✔ | Name of the originating resource or curation effort |
| `organism` | | Default `Homo sapiens` |
| `pmid` | | One or more PMIDs separated by `;` |
| `association_type` | | `expression`, `circulating_biomarker`, `genetic_variant`, `epigenetic`, `functional`, `target_mediated`, `regulatory`, `therapeutic_target`, `other` |
| `regulation_direction` | | `up`, `down`, `not_significant`, `unspecified` |
| `evidence_level` | | `experimental`, `computational_prediction`, `literature_unclear`, `conflicting`, `unverified`. Downgraded with a warning if the row has neither a PMID nor a method. |
| `experimental_methods` | | Free text, e.g. `qRT-PCR; luciferase reporter` |
| `evidence_description` | | Evidence sentence or summary |
| `source_record_id` | | Stable ID in the source (a content hash is generated if absent) |
| `source_url`, `source_version` | | Provenance |
| `gene_symbol`, `gene_entrez_id` | | Gene named by this record for this association |
| `gene_relationship` | | `experimentally_validated_target`, `inferred_target`, `disease_associated_gene`, `indirectly_related` (default `indirectly_related` when a gene is given) |
| `gene_evidence` | | Why the gene is linked |

Example: `data/sample/curated_associations.tsv`.

## Generic ncRNA–gene schema (`generic_targets`)

| Column | Required | Description |
|---|---|---|
| `ncrna_name`, `ncrna_type` | ✔ | As above |
| `gene_symbol` (or `gene_entrez_id`) | ✔ | Normalized through HGNC |
| `relationship` | ✔ | One of the four gene relationships; rows with other values are skipped |
| `source_database` | ✔ | |
| `organism`, `evidence_strength` (`strong`\|`weak`\|`not_stated`), `experimental_methods`, `pmid`, `evidence_description`, `source_record_id` | | `experimentally_validated_target` without a PMID is stored as `inferred_target` with a warning |

Example: `data/sample/curated_targets.tsv`.

## miRTarBase MTI export (`mirtarbase`)

Columns: `miRTarBase ID, miRNA, Species (miRNA), Target Gene, Target Gene (Entrez ID), Species (Target Gene),
Experiments, Support Type, References (PMID)`. "Functional MTI" rows become `strong` evidence and
"(Weak)" rows become `weak`. The adapter was tested against this documented column layout; no miRTarBase file
could be downloaded programmatically during development.

## Sample dataset (`data/sample/`)

The sample is an excerpt of **real** records, with no synthetic data. `manifest.json` records how it was
built. Regenerate it with `python scripts/build_sample_dataset.py`, which requires the raw downloads and
network access.

| File | Content |
|---|---|
| `hmdd_sample.tsv` | Verbatim HMDD rows for 9 miRNAs × 16 diseases (≤6 rows per pair) |
| `lncrnadisease_sample.tsv` | Verbatim LncRNADisease rows for 10 lncRNAs × the same diseases, plus ≤8 non-human rows to show organism labelling |
| `curated_associations.tsv` | 8 hand-curated associations, each checked against the cited PubMed abstract |
| `curated_targets.tsv` | 9 hand-curated miRNA→gene targets, each checked against the cited PubMed abstract |
| `hgnc_subset.tsv` | The HGNC rows needed to resolve the sample's names (all loci of each miRNA stem included) |
| `mesh_cache.json`, `pubmed_cache.json`, `kegg_cache.json` | Cached lookups so the sample imports fully offline |
