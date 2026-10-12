"""Post-import normalization and enrichment.

Usage:
    python scripts/normalize_data.py --diseases [--limit N]   # retry MeSH for unresolved diseases (live)
    python scripts/normalize_data.py --sequences [--limit N]  # fetch miRNA sequences from RNAcentral (live)
    python scripts/normalize_data.py --report                 # write a data-quality report
    python scripts/normalize_data.py --all
"""
import argparse
import json
from datetime import datetime, timezone

from _bootstrap import make_app


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--diseases", action="store_true")
    parser.add_argument("--sequences", action="store_true")
    parser.add_argument("--include-lncrna", action="store_true", help="also fetch lncRNA sequences")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if not any([args.diseases, args.sequences, args.report, args.all]):
        parser.error("choose at least one of --diseases, --sequences, --report, --all")

    app = make_app()
    with app.app_context():
        from app.ingestion import enrichment
        from app.ingestion.runner import build_resolver, load_hgnc
        from app.services.rnacentral import RNAcentralService
        from app.validation.quality import generate_quality_report, save_report

        live = app.config["EXTERNAL_LOOKUPS_ENABLED"]
        if args.diseases or args.all:
            if not live:
                print("Skipping MeSH resolution: external lookups disabled")
            else:
                print("MeSH:", json.dumps(enrichment.reresolve_diseases(build_resolver(True, retry_mesh_misses=True), args.limit)))
        if args.sequences or args.all:
            if not live:
                print("Skipping RNAcentral sequences: external lookups disabled")
            else:
                service = RNAcentralService(timeout=app.config["EXTERNAL_TIMEOUT"])
                print("RNAcentral miRNA:", json.dumps(enrichment.enrich_sequences(service, load_hgnc(), "miRNA",
                                                                                  args.limit)))
                if args.include_lncrna:
                    print("RNAcentral lncRNA:", json.dumps(enrichment.enrich_sequences(service, load_hgnc(),
                                                                                       "lncRNA", args.limit)))
        if args.report or args.all:
            report = generate_quality_report()
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            path = save_report(report, app.config["REPORT_DIR"], f"quality_report_{stamp}")
            print(json.dumps(report["metrics"], indent=2))
            print(f"Report written to {path} (and .csv)")


if __name__ == "__main__":
    main()
