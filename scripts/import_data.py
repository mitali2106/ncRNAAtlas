"""Import data into ncRNAAtlas.

Sample (demonstration) mode — offline, uses files in data/sample/:
    python scripts/import_data.py sample

Real-data mode — run scripts/download_sources.py first:
    python scripts/import_data.py hmdd            [--path data/raw/hmdd_alldata.txt]
    python scripts/import_data.py lncrnadisease   [--path data/raw/lncrnadisease_website_alldata.tsv]
    python scripts/import_data.py real            # HMDD + LncRNADisease + PubMed + KEGG

Other formats:
    python scripts/import_data.py generic    --path my_associations.tsv --source-version 2026-01
    python scripts/import_data.py targets    --path my_targets.tsv
    python scripts/import_data.py mirtarbase --path hsa_MTI.csv --source-version 10.0
    python scripts/import_data.py mirbase    --path miRNA.dat          # sequences + mature aliases
    python scripts/import_data.py pubmed     [--limit 5000]            # fetch pending PubMed metadata

Common options: --dry-run, --human-only, --skip-unresolved, --no-live, --limit N
"""
import argparse
import json
import sys

from _bootstrap import PROJECT_ROOT, make_app

RAW = PROJECT_ROOT / "data" / "raw"
SAMPLE = PROJECT_ROOT / "data" / "sample"
DEFAULT_PATHS = {
    "hmdd": RAW / "hmdd_alldata.txt",
    "lncrnadisease": RAW / "lncrnadisease_website_alldata.tsv",
}
SOURCE_VERSIONS = {"hmdd": "v3.2 (alldata.txt)", "lncrnadisease": "v3.0 (website_alldata.tsv)"}
ADAPTER_FOR = {"hmdd": "hmdd", "lncrnadisease": "lncrnadisease", "generic": "generic_associations",
               "targets": "generic_targets", "mirtarbase": "mirtarbase"}
SAMPLE_STEPS = [
    ("hmdd", SAMPLE / "hmdd_sample.tsv", "v3.2 (sample excerpt)", None),
    ("lncrnadisease", SAMPLE / "lncrnadisease_sample.tsv", "v3.0 (sample excerpt)", None),
    ("generic_associations", SAMPLE / "curated_associations.tsv", "2026-10 (curated sample)", None),
    ("generic_targets", SAMPLE / "curated_targets.tsv", "2026-10 (curated sample)", None),
]


def print_result(label, result, job):
    d = result.to_dict()
    print(f"\n== {label} ==")
    if job is not None:
        print(f"Import job #{job.id}: {job.status}")
    for key in ("raw_records", "valid_records", "inserted", "updated", "unchanged", "skipped",
                "duplicates_in_file", "merged_into_existing", "non_human_records", "missing_pmid"):
        print(f"  {key:<24} {d[key]:>8,}")
    if d["skip_reasons"]:
        print("  skip reasons:", json.dumps(d["skip_reasons"]))
    for kind, rows in d["unresolved"].items():
        print(f"  unresolved {kind}: {len(rows)} distinct names")
    print("  new entities:", json.dumps(d["new_entities"]))
    if d["errors"]:
        print("  ERRORS:", "; ".join(d["errors"]))
    if job is not None and job.report_path:
        print(f"  quality report: {job.report_path}")


def run(adapter, path, args, version=None, label=None, dataset="real"):
    from app.ingestion.runner import run_import

    if not path.exists():
        print(f"File not found: {path}. Run scripts/download_sources.py first or pass --path.", file=sys.stderr)
        sys.exit(2)
    result, job = run_import(
        adapter, path, dataset_label=dataset, source_version=version or args.source_version,
        source_database=args.source_database, dry_run=args.dry_run, skip_unresolved=args.skip_unresolved,
        human_only=args.human_only, live_lookups=False if args.no_live else None, limit=args.limit,
    )
    print_result(label or adapter, result, job)
    if result.errors:
        sys.exit(1)


def pubmed(args):
    from flask import current_app

    from app.ingestion.enrichment import enrich_pubmed
    from app.services.pubmed import PubMedService

    cfg = current_app.config
    if args.no_live or not cfg["EXTERNAL_LOOKUPS_ENABLED"]:
        print("PubMed enrichment skipped (external lookups disabled).")
        return
    service = PubMedService(cfg["NCBI_API_KEY"], cfg["NCBI_EMAIL"], cfg["NCBI_TOOL"], timeout=cfg["EXTERNAL_TIMEOUT"])
    report = enrich_pubmed(service, limit=args.limit)
    print("\n== PubMed metadata ==\n ", json.dumps(report))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["sample", "real", "hmdd", "lncrnadisease", "generic", "targets",
                                            "mirtarbase", "mirbase", "pubmed"])
    parser.add_argument("--path", help="input file path")
    parser.add_argument("--source-version", help="version label recorded with each source record")
    parser.add_argument("--source-database", help="override the source database name (generic formats)")
    parser.add_argument("--dry-run", action="store_true", help="validate and report without writing")
    parser.add_argument("--human-only", action="store_true", help="skip non-human records")
    parser.add_argument("--skip-unresolved", action="store_true", help="skip records with unresolved entities")
    parser.add_argument("--no-live", action="store_true", help="do not call external services (cache only)")
    parser.add_argument("--limit", type=int, help="process at most N records")
    args = parser.parse_args()

    app = make_app()
    with app.app_context():
        from pathlib import Path

        if args.command == "sample":
            args.no_live = True  # sample mode is fully offline and reproducible
            for adapter, path, version, _ in SAMPLE_STEPS:
                run(adapter, path, args, version=version, label=f"sample: {path.name}", dataset="sample")
            from app.ingestion.enrichment import map_kegg_pathways

            cache = json.loads((SAMPLE / "kegg_cache.json").read_text(encoding="utf-8"))
            print("\n== KEGG pathways (cached sample mapping) ==\n ", json.dumps(
                {k: v for k, v in map_kegg_pathways(None, cache).items() if k != "genes_without_pathways"}))
        elif args.command == "real":
            for key in ("hmdd", "lncrnadisease"):
                run(key, DEFAULT_PATHS[key], args, version=SOURCE_VERSIONS[key], label=key)
            # The hand-curated, abstract-checked records are real data too; they supply the
            # gene links that the bulk association files do not contain.
            for adapter, path, version, _ in SAMPLE_STEPS[2:]:
                run(adapter, path, args, version=version, label=f"curated: {path.name}")
            pubmed(args)
            print("\nNext: python scripts/map_pathways.py   (KEGG)  and  python scripts/normalize_data.py --all")
        elif args.command in ("hmdd", "lncrnadisease"):
            path = Path(args.path) if args.path else DEFAULT_PATHS[args.command]
            run(args.command, path, args, version=args.source_version or SOURCE_VERSIONS[args.command])
        elif args.command in ("generic", "targets", "mirtarbase"):
            if not args.path:
                parser.error("--path is required")
            run(ADAPTER_FOR[args.command], Path(args.path), args)
        elif args.command == "mirbase":
            if not args.path:
                parser.error("--path to miRNA.dat is required")
            from app.ingestion.enrichment import apply_mirbase_file

            print(json.dumps(apply_mirbase_file(args.path), indent=2))
        elif args.command == "pubmed":
            pubmed(args)


if __name__ == "__main__":
    main()
