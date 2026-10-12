"""Literature-review workflow for selected ncRNA–disease associations.

Step 1 — triage (retrieves publications and records keyword *hints* only):
    python scripts/validate_associations.py triage --ncrna hsa-mir-21 --disease "Carcinoma, Hepatocellular"
    python scripts/validate_associations.py triage --association-id 12 --fetch

Step 2 — export a review worksheet (one row per association × PMID):
    python scripts/validate_associations.py worksheet --ncrna hsa-mir-21 --out data/reports/review_sheet.csv

Step 3 — record a curator decision after reading the publication:
    python scripts/validate_associations.py review --association-id 12 --pmid 17681183 \
        --outcome supports_direct_experimental --evidence-type "luciferase reporter" --reviewer "A. Curator"

Step 4 — import a completed worksheet (columns: association_id, pmid, outcome, evidence_type, notes, reviewer):
    python scripts/validate_associations.py import-worksheet --path data/reports/review_sheet.csv

Keyword co-occurrence is never treated as proof. Only curator reviews change
an association's validation status.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

from _bootstrap import make_app


def select_associations(args):
    from sqlalchemy import func, select

    from app.extensions import db
    from app.models import Association, Disease, NcRNA

    stmt = select(Association).join(NcRNA).join(Disease)
    if args.association_id:
        stmt = stmt.where(Association.id.in_(args.association_id))
    if args.ncrna:
        stmt = stmt.where(func.lower(NcRNA.canonical_name) == args.ncrna.lower())
    if args.disease:
        stmt = stmt.where(func.lower(Disease.canonical_name) == args.disease.lower())
    return db.session.execute(stmt.order_by(Association.id).limit(args.limit)).scalars().all()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["triage", "worksheet", "review", "import-worksheet", "queue"])
    parser.add_argument("--association-id", type=int, action="append")
    parser.add_argument("--ncrna")
    parser.add_argument("--disease")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--fetch", action="store_true", help="fetch missing PubMed metadata during triage")
    parser.add_argument("--pmid")
    parser.add_argument("--outcome")
    parser.add_argument("--evidence-type")
    parser.add_argument("--notes")
    parser.add_argument("--reviewer")
    parser.add_argument("--out", default=None)
    parser.add_argument("--path")
    args = parser.parse_args()

    app = make_app()
    with app.app_context():
        from app.extensions import db
        from app.models import Association
        from app.models.constants import REVIEW_OUTCOMES
        from app.validation.literature_review import ReviewError, record_review, review_queue, triage_association

        if args.command == "queue":
            for a in review_queue(args.limit):
                print(f"#{a.id}\t{a.ncrna.canonical_name}\t{a.disease.canonical_name}\t{a.association_type}\t"
                      f"{a.evidence_level}\t{a.validation_status}\t{len(a.publication_links)} PMIDs")
            return

        if args.command == "triage":
            service = None
            if args.fetch and app.config["EXTERNAL_LOOKUPS_ENABLED"]:
                from app.services.pubmed import PubMedService

                cfg = app.config
                service = PubMedService(cfg["NCBI_API_KEY"], cfg["NCBI_EMAIL"], cfg["NCBI_TOOL"])
            assocs = select_associations(args)
            if not assocs:
                sys.exit("No matching associations.")
            for a in assocs:
                reviews = triage_association(a, service)
                db.session.commit()
                print(f"#{a.id} {a.ncrna.canonical_name} – {a.disease.canonical_name} [{a.association_type}] "
                      f"→ status {a.validation_status}")
                for r in reviews:
                    f = r.flags
                    print(f"   PMID {r.pmid}: metadata={f['metadata_available']} ncRNA mentions={f['ncrna_mentions']} "
                          f"disease mentions={f['disease_mentions']} manual={f['needs_manual_assessment']}")
            print("\nHints are not evidence. Record curator decisions with the 'review' command.")

        elif args.command == "worksheet":
            assocs = select_associations(args)
            out = Path(args.out or app.config["REPORT_DIR"] / "review_worksheet.csv")
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["association_id", "ncrna", "disease", "association_type", "source_evidence_level",
                            "pmid", "title", "year", "pubmed_url", "outcome", "evidence_type", "notes", "reviewer"])
                for a in assocs:
                    for link in a.publication_links:
                        p = link.publication
                        w.writerow([a.id, a.ncrna.canonical_name, a.disease.canonical_name, a.association_type,
                                    a.evidence_level, p.pmid, p.publication_title or "", p.publication_year or "",
                                    p.publication_url, "", "", "", ""])
            print(f"Worksheet written to {out}. Allowed outcomes: {', '.join(REVIEW_OUTCOMES)}")

        elif args.command == "review":
            if not (args.association_id and args.outcome and args.reviewer):
                parser.error("review requires --association-id, --outcome and --reviewer")
            a = db.session.get(Association, args.association_id[0])
            if a is None:
                sys.exit("Association not found")
            try:
                record_review(a, args.outcome, pmid=args.pmid, evidence_type=args.evidence_type, notes=args.notes,
                              reviewer=args.reviewer)
            except ReviewError as exc:
                sys.exit(f"Error: {exc}")
            db.session.commit()
            print(f"Recorded. Association #{a.id} validation status: {a.validation_status}")

        elif args.command == "import-worksheet":
            if not args.path:
                parser.error("--path is required")
            done, errors = 0, []
            with open(args.path, newline="", encoding="utf-8") as fh:
                for i, row in enumerate(csv.DictReader(fh), start=2):
                    if not (row.get("outcome") or "").strip():
                        continue
                    a = db.session.get(Association, int(row["association_id"]))
                    try:
                        if a is None:
                            raise ReviewError("association not found")
                        record_review(a, row["outcome"].strip(), pmid=(row.get("pmid") or "").strip() or None,
                                      evidence_type=row.get("evidence_type") or None, notes=row.get("notes") or None,
                                      reviewer=(row.get("reviewer") or "").strip() or None)
                        done += 1
                    except ReviewError as exc:
                        errors.append({"line": i, "error": str(exc)})
            db.session.commit()
            print(json.dumps({"reviews_recorded": done, "errors": errors}, indent=2))


if __name__ == "__main__":
    main()
