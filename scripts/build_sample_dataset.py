"""Regenerate the sample dataset in data/sample/ from the raw downloads.

The sample is an *excerpt of real records* (no synthetic data):
  * hmdd_sample.tsv            – rows copied verbatim from HMDD alldata.txt
  * lncrnadisease_sample.tsv   – rows copied verbatim from LncRNADisease website_alldata.tsv
  * curated_associations.tsv   – hand-curated rows, each checked against its PubMed abstract (not regenerated)
  * curated_targets.tsv        – hand-curated miRNA→gene targets (not regenerated)
  * hgnc_subset.tsv            – HGNC rows needed to resolve the sample's entities
  * mesh_cache.json            – exact MeSH descriptor lookups for the sample's diseases
  * pubmed_cache.json          – PubMed metadata for every cited PMID
  * kegg_cache.json            – KEGG gene→pathway links for the sample's genes
  * manifest.json              – provenance of all of the above

Requires network access (MeSH, PubMed, KEGG) and the raw files from
scripts/download_sources.py. Usage:  python scripts/build_sample_dataset.py
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

from _bootstrap import PROJECT_ROOT  # noqa: F401  (adds backend to sys.path)

from app.ingestion.adapters import HMDDAdapter
from app.normalization.mirna import parse_mirna
from app.services.hgnc import HGNCIndex
from app.services.kegg import KEGGService
from app.services.mesh import MeSHService
from app.services.pubmed import PubMedService

RAW = PROJECT_ROOT / "data" / "raw"
SAMPLE = PROJECT_ROOT / "data" / "sample"
csv.field_size_limit(50 * 1024 * 1024)

MIRNAS = ["hsa-mir-21", "hsa-mir-155", "hsa-mir-34a", "hsa-mir-15a", "hsa-mir-16-1", "hsa-mir-16",
          "hsa-mir-122", "hsa-mir-145", "hsa-let-7a-1"]
LNCRNAS = ["MALAT1", "HOTAIR", "H19", "MEG3", "NEAT1", "PVT1", "CDKN2B-AS1", "GAS5", "LINC00152", "XIST"]
DISEASES = ["Carcinoma, Hepatocellular", "Breast Neoplasms", "Lung Neoplasms", "Carcinoma, Non-Small-Cell Lung",
            "Colorectal Neoplasms", "Glioblastoma", "Glioma", "Leukemia, Lymphocytic, Chronic, B-Cell",
            "Stomach Neoplasms", "Prostatic Neoplasms", "Pancreatic Neoplasms", "Osteosarcoma",
            "Carcinoma, Renal Cell", "Diabetes Mellitus, Type 2", "Alzheimer Disease", "Atrial Fibrillation"]
MAX_PER_PAIR = 6
MAX_NON_HUMAN = 8


def read_tsv(path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        return reader.fieldnames, list(reader)


def write_tsv(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def clean(v):
    return (v or "").strip().strip('"').strip()


def main():
    hmdd_path, lnc_path = RAW / "hmdd_alldata.txt", RAW / "lncrnadisease_website_alldata.tsv"
    hgnc_path = RAW / "hgnc_complete_set.txt"
    for p in (hmdd_path, lnc_path, hgnc_path):
        if not p.exists():
            sys.exit(f"Missing {p}. Run scripts/download_sources.py first.")
    disease_set = {d.lower() for d in DISEASES}

    # HMDD contains some non-UTF-8 (GBK) lines; read with the adapter's decoding
    # fallbacks and write the excerpt as UTF-8.
    hmdd_adapter = HMDDAdapter()
    rows = [r for _, r in hmdd_adapter.read_rows(hmdd_path)]
    header = list(HMDDAdapter.required_columns)
    per_pair, hmdd_rows = Counter(), []
    for r in rows:
        mir, dis = clean(r["mir"]).lower(), clean(r["disease"])
        if mir in MIRNAS and dis.lower() in disease_set and per_pair[(mir, dis)] < MAX_PER_PAIR:
            per_pair[(mir, dis)] += 1
            hmdd_rows.append(r)
    write_tsv(SAMPLE / "hmdd_sample.tsv", header, hmdd_rows)

    header, rows = read_tsv(lnc_path)
    lnc_set = {x.lower() for x in LNCRNAS}
    per_pair, lnc_rows, non_human = Counter(), [], 0
    for r in rows:
        if clean(r["ncRNA Category"]) != "LncRNA" or clean(r["ncRNA Symbol"]).lower() not in lnc_set:
            continue
        species, dis = clean(r["Species"]), clean(r["Disease Name"])
        if species != "Homo sapiens":
            if non_human < MAX_NON_HUMAN:
                non_human += 1
                lnc_rows.append(r)
            continue
        key = (clean(r["ncRNA Symbol"]).lower(), dis)
        if dis.lower() in disease_set and per_pair[key] < MAX_PER_PAIR:
            per_pair[key] += 1
            lnc_rows.append(r)
    write_tsv(SAMPLE / "lncrnadisease_sample.tsv", header, lnc_rows)

    _, curated = read_tsv(SAMPLE / "curated_associations.tsv")
    _, targets = read_tsv(SAMPLE / "curated_targets.tsv")

    # HGNC subset: every symbol needed for resolution, plus all loci of each miRNA stem
    hgnc = HGNCIndex.from_file(hgnc_path)
    symbols = set()
    mir_names = {clean(r["mir"]) for r in hmdd_rows} | {r["ncrna_name"] for r in curated + targets
                                                         if r["ncrna_type"] == "miRNA"}
    for name in mir_names:
        parsed = parse_mirna(name)
        if parsed:
            symbols.add(parsed.hgnc_symbol)
            symbols.update(hgnc.mirna_loci(parsed.hgnc_base))
    lnc_names = {clean(r["ncRNA Symbol"]) for r in lnc_rows} | {r["ncrna_name"] for r in curated
                                                                if r["ncrna_type"] == "lncRNA"}
    gene_names = {r["gene_symbol"] for r in curated + targets if r.get("gene_symbol")}
    for name in lnc_names | gene_names:
        rec, _, cands = hgnc.lookup(name)
        if rec:
            symbols.add(rec.symbol)
        symbols.update(c.symbol for c in cands)
    n_hgnc = hgnc.write_subset(SAMPLE / "hgnc_subset.tsv", symbols)

    # MeSH exact-label lookups
    mesh = MeSHService()
    disease_names = ({clean(r["disease"]) for r in hmdd_rows} | {clean(r["Disease Name"]) for r in lnc_rows}
                     | {r["disease_name"] for r in curated})
    mesh_cache = {name.lower(): mesh.lookup_descriptor(name) for name in sorted(disease_names)}
    (SAMPLE / "mesh_cache.json").write_text(json.dumps(mesh_cache, indent=1, sort_keys=True), encoding="utf-8")

    # PubMed metadata for every cited PMID
    pmids = ({clean(r["pmid"]) for r in hmdd_rows} | {clean(r["PubMed ID"]) for r in lnc_rows}
             | {r["pmid"] for r in curated + targets})
    pmids = sorted(p for p in pmids if p.isdigit())
    pubmed = PubMedService()
    pub_cache = pubmed.fetch(pmids)
    (SAMPLE / "pubmed_cache.json").write_text(json.dumps(pub_cache, indent=1, sort_keys=True), encoding="utf-8")

    # KEGG links for every resolvable gene
    entrez = {}
    for g in gene_names:
        rec, _, _ = hgnc.lookup(g)
        if rec and rec.entrez_id and rec.locus_group == "protein-coding gene":
            entrez[rec.entrez_id] = rec.symbol
    kegg = KEGGService()
    names = kegg.list_human_pathways()
    links = kegg.link_genes(sorted(entrez))
    used = {p for ps in links.values() for p in ps}
    retrieved = datetime.now(timezone.utc).date().isoformat()
    (SAMPLE / "kegg_cache.json").write_text(json.dumps({
        "retrieved_at": retrieved, "source": "https://rest.kegg.jp (link/pathway, list/pathway/hsa)",
        "links": links, "pathway_names": {p: names.get(p) for p in sorted(used)},
    }, indent=1, sort_keys=True), encoding="utf-8")

    raw_manifest = json.loads((RAW / "manifest.json").read_text()) if (RAW / "manifest.json").exists() else {}
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_label": "sample",
        "synthetic_records": 0,
        "description": "Excerpt of real source records for demonstration. Not a complete or representative "
                       "dataset; counts shown in sample mode describe the excerpt only.",
        "selection": {"mirnas": MIRNAS, "lncrnas": LNCRNAS, "diseases": DISEASES,
                      "max_records_per_ncrna_disease_pair": MAX_PER_PAIR, "max_non_human_lncrnadisease_rows": MAX_NON_HUMAN},
        "files": {
            "hmdd_sample.tsv": {"rows": len(hmdd_rows), "from": raw_manifest.get("hmdd")},
            "lncrnadisease_sample.tsv": {"rows": len(lnc_rows), "non_human_rows": non_human,
                                         "from": raw_manifest.get("lncrnadisease")},
            "curated_associations.tsv": {"rows": len(curated), "method": "hand-curated; every claim checked "
                                         "against the PubMed abstract of the cited PMID"},
            "curated_targets.tsv": {"rows": len(targets), "method": "hand-curated; every claim checked against "
                                    "the PubMed abstract of the cited PMID"},
            "hgnc_subset.tsv": {"rows": n_hgnc, "from": raw_manifest.get("hgnc")},
            "mesh_cache.json": {"lookups": len(mesh_cache), "resolved": sum(1 for v in mesh_cache.values() if v)},
            "pubmed_cache.json": {"requested": len(pmids), "retrieved": len(pub_cache)},
            "kegg_cache.json": {"genes": len(entrez), "genes_with_pathways": sum(1 for v in links.values() if v),
                                "pathways": len(used), "retrieved_at": retrieved},
        },
    }
    (SAMPLE / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest["files"], indent=2, default=str))
    by_mir = defaultdict(int)
    for r in hmdd_rows:
        by_mir[clean(r["mir"])] += 1
    print("HMDD rows per miRNA:", dict(by_mir))


if __name__ == "__main__":
    main()
