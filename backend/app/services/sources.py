"""Registry describing every external resource used by ncRNAAtlas.

Descriptions state what each resource is used for *and what it is not used
for*. Access notes reflect what was verified during development; licensing
terms must be checked against each provider's current policy before reuse.
"""
from sqlalchemy import func, select

from ..extensions import db
from ..models import AssociationSource, ImportJob, NcRNAGeneInteraction

SOURCES = [
    {
        "key": "HMDD", "citation_pmids": ["30364956", "37650649"],
        "name": "HMDD — Human microRNA Disease Database (v3.2)",
        "role": "miRNA–disease associations",
        "purpose": "Experimentally supported human miRNA–disease association records curated from the literature, "
                   "each with an evidence category and PMID.",
        "not_used_for": "HMDD categories are mapped to evidence levels by documented rules; an HMDD entry is not "
                        "treated as independent validation.",
        "access": "Bulk download of 'alldata.txt' (tab-separated) from the HMDD website.",
        "url": "http://www.cuilab.cn/hmdd",
        "download_url": "http://www.cuilab.cn/static/hmdd3/data/alldata.txt",
        "citation": "Cui C, et al. HMDD v4.0: a database for experimentally supported human microRNA-disease "
                    "associations. Nucleic Acids Res. 2024;52(D1):D1327-D1332. (v3.2 data file used here: "
                    "Huang Z, et al. Nucleic Acids Res. 2019;47(D1):D1013-D1017.)",
        "license": "Freely available for academic use; check the HMDD website for current terms.",
    },
    {
        "key": "LncRNADisease", "citation_pmids": ["37819033"],
        "name": "LncRNADisease v3.0",
        "role": "lncRNA–disease associations",
        "purpose": "Experimentally supported lncRNA/circRNA–disease records with species, dysfunction pattern, "
                   "validation method, description and PMID. Only lncRNA rows are imported.",
        "not_used_for": "circRNA records are skipped (ncRNAAtlas models miRNA and lncRNA only).",
        "access": "Bulk download 'website_alldata.tsv' from the LncRNADisease download page.",
        "url": "http://www.rnanut.net/lncrnadisease/",
        "download_url": "http://www.rnanut.net/lncrnadisease/static/download/website_alldata.tsv",
        "citation": "Lin X, et al. LncRNADisease v3.0: an updated database of long non-coding RNA-associated "
                    "diseases. Nucleic Acids Res. 2024;52(D1):D1365-D1369.",
        "license": "Freely available for academic use; check the website for current terms.",
    },
    {
        "key": "HGNC", "citation_pmids": ["36243972"],
        "name": "HGNC — HUGO Gene Nomenclature Committee",
        "role": "Nomenclature and identifier normalization",
        "purpose": "Approved symbols, previous symbols and aliases for genes, lncRNAs and miRNA loci; cross-references "
                   "to NCBI Gene, miRBase and RNAcentral identifiers.",
        "not_used_for": "Not a source of disease associations.",
        "access": "Complete-set TSV download (a subset ships with the sample dataset).",
        "url": "https://www.genenames.org/",
        "download_url": "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt",
        "citation": "Seal RL, et al. Genenames.org: the HGNC resources in 2023. Nucleic Acids Res. 2023;51(D1):D1003-D1009.",
        "license": "CC0 1.0",
    },
    {
        "key": "miRBase", "citation_pmids": ["30423142"],
        "name": "miRBase",
        "role": "miRNA identifiers, names and sequences",
        "purpose": "Reference miRNA nomenclature and precursor/mature sequences.",
        "not_used_for": "miRBase entries are never treated as evidence of a disease association.",
        "access": "Flat file 'miRNA.dat' parsed from a local download. The miRBase website was unreachable during "
                  "development, so precursor accessions are taken from HGNC cross-references unless a file is imported.",
        "url": "https://www.mirbase.org/",
        "download_url": "https://www.mirbase.org/download/",
        "citation": "Kozomara A, Birgaoanu M, Griffiths-Jones S. miRBase: from microRNA sequences to function. "
                    "Nucleic Acids Res. 2019;47(D1):D155-D162.",
        "license": "Public domain / freely available (see miRBase).",
    },
    {
        "key": "RNAcentral", "citation_pmids": ["33106848"],
        "name": "RNAcentral",
        "role": "RNA identity and sequences",
        "purpose": "URS identifiers and sequences for ncRNAs, via the public REST API.",
        "not_used_for": "RNAcentral entries are never treated as evidence of a disease association.",
        "access": "REST API (https://rnacentral.org/api/v1).",
        "url": "https://rnacentral.org/",
        "download_url": None,
        "citation": "RNAcentral Consortium. RNAcentral 2021: secondary structure integration, improved sequence "
                    "search and new member databases. Nucleic Acids Res. 2021;49(D1):D212-D220.",
        "license": "CC0 1.0",
    },
    {
        "key": "PubMed", "citation_pmids": ["37994677"],
        "name": "PubMed (NCBI Entrez E-utilities)",
        "role": "Bibliographic metadata",
        "purpose": "Title, authors, journal, year, abstract and DOI for PMIDs cited by source records; "
                   "literature search.",
        "not_used_for": "A publication mentioning an RNA and a disease is not treated as proof of an association.",
        "access": "E-utilities esearch/esummary/efetch; ≤3 requests/s without an API key.",
        "url": "https://pubmed.ncbi.nlm.nih.gov/",
        "download_url": None,
        "citation": "Sayers EW, et al. Database resources of the National Center for Biotechnology Information. "
                    "Nucleic Acids Res. 2024;52(D1):D33-D43.",
        "license": "NCBI usage policies; abstracts may be copyrighted by publishers.",
    },
    {
        "key": "KEGG", "citation_pmids": ["39417505"],
        "name": "KEGG PATHWAY (REST API)",
        "role": "Gene-to-pathway mapping",
        "purpose": "Maps human genes (by NCBI Gene ID) to KEGG pathway identifiers and names.",
        "not_used_for": "KEGG does not establish ncRNA–disease associations; ncRNA/disease pathways are inferred "
                        "through associated genes and labelled as such.",
        "access": "KEGG REST API (link/pathway, list/pathway), academic use.",
        "url": "https://www.kegg.jp/kegg/pathway.html",
        "download_url": None,
        "citation": "Kanehisa M, et al. KEGG: biological systems database as a model of the real world. "
                    "Nucleic Acids Res. 2025;53(D1):D672-D677.",
        "license": "KEGG REST is free for academic use; see https://www.kegg.jp/kegg/legal.html.",
    },
    {
        "key": "MeSH", "citation_pmids": [],
        "name": "MeSH (NLM Medical Subject Headings)",
        "role": "Disease identifier normalization",
        "purpose": "Exact-label lookup of disease names to MeSH descriptor IDs.",
        "not_used_for": "No fuzzy matching; names without an exact descriptor match stay unresolved.",
        "access": "MeSH RDF lookup API (https://id.nlm.nih.gov/mesh/).",
        "url": "https://www.nlm.nih.gov/mesh/",
        "download_url": None,
        "citation": "National Library of Medicine. Medical Subject Headings.",
        "license": "Public domain (NLM terms and conditions).",
    },
    {
        "key": "miRTarBase", "citation_pmids": ["39578692"],
        "name": "miRTarBase (optional import format)",
        "role": "miRNA–target interactions",
        "purpose": "Experimentally validated miRNA–target interactions, importable from a user-downloaded MTI file.",
        "not_used_for": "Target relationships are not disease-specific and are shown separately from associations.",
        "access": "The download page requires a browser; files must be downloaded manually and imported with the "
                  "'mirtarbase' adapter.",
        "url": "https://mirtarbase.cuhk.edu.cn/",
        "download_url": None,
        "citation": "Cui S, et al. miRTarBase 2025: updates to the collection of experimentally validated "
                    "microRNA-target interactions. Nucleic Acids Res. 2025;53(D1):D147-D156.",
        "license": "Check the miRTarBase website for current terms.",
    },
]


def sources_with_status():
    assoc_counts = dict(db.session.execute(
        select(AssociationSource.source_database, func.count(AssociationSource.id))
        .group_by(AssociationSource.source_database)
    ).all())
    inter_counts = dict(db.session.execute(
        select(NcRNAGeneInteraction.source_database, func.count(NcRNAGeneInteraction.id))
        .group_by(NcRNAGeneInteraction.source_database)
    ).all())
    jobs = db.session.execute(
        select(ImportJob).where(ImportJob.status.like("completed%")).order_by(ImportJob.completed_at.desc())
    ).scalars().all()
    last_job = {}
    for j in jobs:
        last_job.setdefault(j.source_database, j)
    out = []
    known = set()
    for s in SOURCES:
        known.add(s["key"])
        j = last_job.get(s["key"])
        out.append({**s, "association_source_records": assoc_counts.get(s["key"], 0),
                    "ncrna_gene_records": inter_counts.get(s["key"], 0),
                    "last_import": {"completed_at": j.completed_at.isoformat() if j and j.completed_at else None,
                                    "source_version": j.source_version if j else None,
                                    "dataset_label": j.dataset_label if j else None,
                                    "job_id": j.id if j else None} if j else None})
    for name in sorted(set(assoc_counts) | set(inter_counts)):
        if name not in known:
            j = last_job.get(name)
            out.append({"key": name, "name": name, "role": "Imported dataset", "purpose": "User-imported records",
                        "association_source_records": assoc_counts.get(name, 0),
                        "ncrna_gene_records": inter_counts.get(name, 0),
                        "last_import": {"completed_at": j.completed_at.isoformat() if j and j.completed_at else None,
                                        "source_version": j.source_version, "dataset_label": j.dataset_label,
                                        "job_id": j.id} if j else None})
    return out
