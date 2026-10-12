"""Shared pytest fixtures. External services are never contacted by the tests."""
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from config import TestingConfig  # noqa: E402

ADMIN = {"X-Admin-Token": "test-admin-token"}

GENERIC_ASSOCIATIONS = (
    "ncrna_name\tncrna_type\tdisease_name\tsource_database\torganism\tpmid\tassociation_type\t"
    "regulation_direction\tevidence_level\texperimental_methods\tevidence_description\tsource_record_id\t"
    "gene_symbol\tgene_relationship\tgene_evidence\n"
    "hsa-mir-21\tmiRNA\tCarcinoma, Hepatocellular\tTest curation\tHomo sapiens\t17681183\ttarget_mediated\t"
    "unspecified\texperimental\tqRT-PCR\tPTEN direct target (abstract)\tt-1\tPTEN\texperimentally_validated_target\t"
    "Direct target per abstract\n"
    "LINC00152\tlncRNA\tCarcinoma, Hepatocellular\tTest curation\tHomo sapiens\t16166262\texpression\tup\t\t"
    "qRT-PCR\tUp in tumour\tt-2\t\t\t\n"
    "LINC00152\tlncRNA\tCarcinoma, Hepatocellular\tTest curation\tHomo sapiens\t17616664\texpression\tdown\t\t"
    "qRT-PCR\tDown in tumour\tt-3\t\t\t\n"
    "LINC00152\tlncRNA\tCarcinoma, Hepatocellular\tTest curation\tHomo sapiens\t17616664\texpression\tdown\t\t"
    "qRT-PCR\tDown in tumour\tt-3\t\t\t\n"
    "hsa-mir-155\tmiRNA\tLiver cancer of hepatocytes\tTest curation\tHomo sapiens\tnot-a-pmid\tother\t\texperimental\t"
    "\t\tt-4\t\t\t\n"
    "MALAT1\tlncRNA\tBreast Neoplasms\tTest curation\tMus musculus\t20393566\texpression\tup\t\tqRT-PCR\t\tt-5\t\t\t\n"
    "XYZ1\tcircRNA\tBreast Neoplasms\tTest curation\tHomo sapiens\t20393566\texpression\tup\t\t\t\tt-6\t\t\t\n"
)

GENERIC_TARGETS = (
    "ncrna_name\tncrna_type\tgene_symbol\trelationship\tsource_database\torganism\tevidence_strength\t"
    "experimental_methods\tpmid\tevidence_description\tsource_record_id\n"
    "hsa-mir-21\tmiRNA\tPTEN\texperimentally_validated_target\tTest curation\tHomo sapiens\tnot_stated\t\t17681183\t"
    "Direct target per abstract\ttg-1\n"
    "hsa-mir-21\tmiRNA\tMMAC1\texperimentally_validated_target\tTest curation\tHomo sapiens\tstrong\tLuciferase\t"
    "16166262\tAlias symbol of PTEN\ttg-2\n"
    "hsa-mir-15a\tmiRNA\tBCL2\texperimentally_validated_target\tTest curation\tHomo sapiens\t\t\t\tNo PMID\ttg-3\n"
    "hsa-mir-155\tmiRNA\tSOCS1\tbogus_relationship\tTest curation\tHomo sapiens\t\t\t20354188\t\ttg-4\n"
)


@pytest.fixture
def app(tmp_path):
    class Cfg(TestingConfig):
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + (tmp_path / "test.db").as_posix()
        HGNC_PATH = str(FIXTURES / "hgnc_small.tsv")
        SAMPLE_DIR = FIXTURES
        RAW_DIR = tmp_path / "raw"
        UPLOAD_DIR = tmp_path / "uploads"
        REPORT_DIR = tmp_path / "reports"

    application = create_app(Cfg)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def write_file(tmp_path):
    def _write(name, content):
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def loaded(app, write_file):
    """Database populated from real fixture rows plus small curated test files and KEGG links."""
    from app.ingestion.enrichment import map_kegg_pathways
    from app.ingestion.runner import run_import
    from app.services.kegg import parse_link, parse_pathway_list

    results = {
        "hmdd": run_import("hmdd", FIXTURES / "hmdd_small.tsv", source_version="test"),
        "lnc": run_import("lncrnadisease", FIXTURES / "lncrnadisease_small.tsv", source_version="test"),
        "generic": run_import("generic_associations", write_file("assoc.tsv", GENERIC_ASSOCIATIONS)),
        "targets": run_import("generic_targets", write_file("targets.tsv", GENERIC_TARGETS)),
    }
    cache = {
        "retrieved_at": "test",
        "links": parse_link((FIXTURES / "kegg_link.txt").read_text()),
        "pathway_names": parse_pathway_list((FIXTURES / "kegg_list.txt").read_text()),
    }
    results["kegg"] = map_kegg_pathways(None, cache)
    return results
