"""Map human genes (with NCBI Gene IDs) to KEGG pathways.

Usage:
    python scripts/map_pathways.py            # live KEGG REST API, falls back to the sample cache
    python scripts/map_pathways.py --offline  # use data/sample/kegg_cache.json only
    python scripts/map_pathways.py --all      # re-check genes that already have mappings

Only genes whose NCBI Gene ID was resolved through HGNC are mapped; genes
without a reliable identifier are reported, never guessed.
"""
import argparse
import json

from _bootstrap import PROJECT_ROOT, make_app


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--all", action="store_true", help="include genes that already have a mapping")
    args = parser.parse_args()
    app = make_app()
    with app.app_context():
        from app.ingestion.enrichment import map_kegg_pathways
        from app.services.kegg import KEGGService

        cache_path = PROJECT_ROOT / "data" / "sample" / "kegg_cache.json"
        cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else None
        live = not args.offline and app.config["EXTERNAL_LOOKUPS_ENABLED"]
        service = KEGGService(timeout=app.config["EXTERNAL_TIMEOUT"]) if live else None
        report = map_kegg_pathways(service, cache, only_unmapped=not args.all)
        missing = report.pop("genes_without_pathways")
        print(json.dumps(report, indent=2))
        if missing:
            print(f"{len(missing)} genes have no KEGG pathway: {', '.join(missing[:30])}{' ...' if len(missing) > 30 else ''}")


if __name__ == "__main__":
    main()
