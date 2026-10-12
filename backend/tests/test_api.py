"""REST API: search, filtering, pagination, errors, external failures, admin workflow."""
import io

import pytest

from app.extensions import db
from app.models import Association, Disease, Gene, NcRNA
from app.services.http_client import ExternalServiceError
from conftest import ADMIN, GENERIC_ASSOCIATIONS


def ids(model, **kw):
    return db.session.query(model).filter_by(**kw).one().id


# ---------------------------------------------------------------- metadata
def test_health(client):
    body = client.get("/api/health").get_json()["data"]
    assert body["status"] == "ok" and body["database"]["connected"]
    assert body["admin_enabled"] is True


def test_statistics_empty_state(client):
    data = client.get("/api/statistics").get_json()["data"]
    assert data["is_empty"] is True
    assert data["totals"]["associations"] == 0 and data["top_diseases"] == []


def test_statistics_reflect_database(client, loaded):
    data = client.get("/api/statistics").get_json()["data"]
    assert data["is_empty"] is False
    assert data["totals"]["associations"] == db.session.query(Association).count()
    assert data["totals"]["ncrnas"] == db.session.query(NcRNA).count()
    assert data["totals"]["genes"] == db.session.query(Gene).count()
    assert set(data["ncrna_type_distribution"]) == {"miRNA", "lncRNA"}
    assert data["top_diseases"][0]["association_count"] >= data["top_diseases"][-1]["association_count"]
    assert data["totals"]["mapped_pathways"] > 0
    assert data["recent_imports"]


def test_sources_and_import_jobs(client, loaded):
    sources = {s["key"]: s for s in client.get("/api/sources").get_json()["data"]}
    assert sources["HMDD"]["association_source_records"] > 0
    assert sources["HMDD"]["last_import"]["source_version"] == "test"
    assert "Test curation" in sources  # user-imported dataset is listed with provenance
    jobs = client.get("/api/import-jobs?per_page=2").get_json()
    assert jobs["pagination"]["total"] == 4 and len(jobs["data"]) == 2
    assert client.get("/api/import-jobs/999").status_code == 404


# ------------------------------------------------------------------ ncRNAs
def test_ncrna_search_by_alias_identifier_and_type(client, loaded):
    by_alias = client.get("/api/ncrnas?q=MIR21").get_json()["data"]
    assert by_alias[0]["canonical_name"] == "hsa-mir-21"
    by_acc = client.get("/api/ncrnas?q=MI0000077").get_json()["data"]
    assert [n["canonical_name"] for n in by_acc] == ["hsa-mir-21"]
    by_old_name = client.get("/api/ncrnas?q=linc00152").get_json()["data"]
    assert by_old_name[0]["canonical_name"] == "CYTOR"
    lnc = client.get("/api/ncrnas?type=lncRNA&per_page=100").get_json()["data"]
    assert lnc and all(n["ncrna_type"] == "lncRNA" for n in lnc)
    assert all(n["organism"] == "Homo sapiens" for n in lnc)
    mouse = client.get("/api/ncrnas?organism=Mus musculus").get_json()["data"]
    assert len(mouse) == 2


def test_ncrna_pagination_and_validation(client, loaded):
    page1 = client.get("/api/ncrnas?per_page=2&page=1&sort=name").get_json()
    page2 = client.get("/api/ncrnas?per_page=2&page=2&sort=name").get_json()
    assert page1["pagination"]["per_page"] == 2 and page1["pagination"]["total"] >= 4
    assert {n["id"] for n in page1["data"]}.isdisjoint({n["id"] for n in page2["data"]})
    assert client.get("/api/ncrnas?per_page=1000").status_code == 400
    assert client.get("/api/ncrnas?page=abc").status_code == 400
    assert client.get("/api/ncrnas?type=snoRNA").status_code == 400
    err = client.get("/api/ncrnas/99999").get_json()
    assert err["error"]["status"] == 404 and err["error"]["code"] == "not_found"


def test_ncrna_detail_subresources(client, loaded):
    mir21 = ids(NcRNA, canonical_name="hsa-mir-21")
    d = client.get(f"/api/ncrnas/{mir21}").get_json()["data"]
    assert d["stable_identifier"] == "MI0000077" and d["identifier_url"].endswith("MI0000077")
    assert any(i["namespace"] == "HGNC" for i in d["aliases"]["identifiers"])
    assert d["counts"]["associations"] > 0
    assoc = client.get(f"/api/ncrnas/{mir21}/associations?evidence_level=experimental").get_json()
    assert assoc["data"] and all(a["evidence_level"] == "experimental" for a in assoc["data"])
    genes = client.get(f"/api/ncrnas/{mir21}/genes").get_json()["data"]
    assert {i["gene"]["approved_gene_symbol"] for i in genes["interactions"]} == {"PTEN"}
    assert genes["association_gene_links"][0]["scope"] == "association"
    pw = client.get(f"/api/ncrnas/{mir21}/pathways").get_json()["data"]
    assert pw["pathways"] and all(p["mapping_type"] == "inferred_via_genes" for p in pw["pathways"])


def test_entity_with_no_associations(client, loaded):
    gene = db.session.query(Gene).filter_by(approved_gene_symbol="BCL2").one()
    data = client.get(f"/api/genes/{gene.id}/associations").get_json()["data"]
    assert data["direct"] == []  # exists, but has no association-specific links


# ---------------------------------------------------------- associations
def test_association_filters_combine(client, loaded):
    all_ = client.get("/api/associations?per_page=100").get_json()
    hmdd = client.get("/api/associations?source=HMDD&per_page=100").get_json()
    combined = client.get("/api/associations?source=HMDD&ncrna_type=miRNA&evidence_level=experimental"
                          "&disease=hepatocellular&per_page=100").get_json()
    assert all_["pagination"]["total"] > hmdd["pagination"]["total"] >= combined["pagination"]["total"] > 0
    for a in combined["data"]:
        assert "HMDD" in a["source_databases"] and a["ncrna"]["ncrna_type"] == "miRNA"
        assert "Hepatocellular" in a["disease"]["canonical_name"]
    conflicting = client.get("/api/associations?evidence_level=conflicting&per_page=100").get_json()["data"]
    assert "CYTOR" in {a["ncrna"]["canonical_name"] for a in conflicting}
    for a in conflicting:  # real HMDD rows also report opposite directions for some pairs
        directions = {s["regulation_direction"] for s in
                      client.get(f"/api/associations/{a['id']}/sources").get_json()["data"]}
        assert {"up", "down"} <= directions
    assert client.get("/api/associations?evidence_level=proven").status_code == 400
    assert client.get("/api/associations?sort=random").status_code == 400
    assert client.get("/api/associations?q=zzzz-no-match").get_json()["data"] == []


def test_association_sort_is_stable(client, loaded):
    a = client.get("/api/associations?sort=evidence&per_page=100").get_json()["data"]
    b = client.get("/api/associations?sort=evidence&per_page=100").get_json()["data"]
    assert [x["id"] for x in a] == [x["id"] for x in b]
    pubs = client.get("/api/associations?sort=publications&order=desc&per_page=100").get_json()["data"]
    counts = [x["publication_count"] for x in pubs]
    assert counts == sorted(counts, reverse=True)


def test_association_detail_is_traceable(client, loaded):
    mir21 = ids(NcRNA, canonical_name="hsa-mir-21")
    hcc = ids(Disease, disease_identifier="D006528")
    a = db.session.query(Association).filter_by(ncrna_id=mir21, disease_id=hcc,
                                                association_type="target_mediated").one()
    d = client.get(f"/api/associations/{a.id}").get_json()["data"]
    assert d["genes"][0]["gene"]["approved_gene_symbol"] == "PTEN"
    assert d["genes"][0]["gene_relationship"] == "experimentally_validated_target"
    assert d["pathways"] and d["pathways"][0]["basis"].startswith("Genes linked")
    assert d["validation_status"] == "not_reviewed" and d["confidence_score"] is None
    sources = client.get(f"/api/associations/{a.id}/sources").get_json()["data"]
    assert {s["source_database"] for s in sources} == {"HMDD", "Test curation"}
    assert all(s["original_record"] for s in sources)
    pubs = client.get(f"/api/associations/{a.id}/publications").get_json()["data"]
    assert any(p["pmid"] == "17681183" and p["publication_url"].endswith("/17681183/") for p in pubs)
    assert client.get("/api/associations/99999/sources").status_code == 404


def test_disease_endpoints(client, loaded):
    hcc = ids(Disease, disease_identifier="D006528")
    d = client.get(f"/api/diseases/{hcc}").get_json()["data"]
    assert d["counts"]["mirnas"] >= 2 and d["counts"]["lncrnas"] == 1
    assert d["identifier_url"].endswith("D006528")
    listing = client.get("/api/diseases?q=neoplasms").get_json()["data"]
    assert listing and all("neoplasms" in x["canonical_name"].lower() for x in listing)
    assoc = client.get(f"/api/diseases/{hcc}/associations?ncrna_type=lncRNA").get_json()["data"]
    assert [a["ncrna"]["canonical_name"] for a in assoc] == ["CYTOR"]
    genes = client.get(f"/api/diseases/{hcc}/genes").get_json()["data"]
    assert genes[0]["gene"]["approved_gene_symbol"] == "PTEN"


def test_gene_endpoints_separate_direct_and_indirect(client, loaded):
    pten = ids(Gene, approved_gene_symbol="PTEN")
    d = client.get(f"/api/genes/{pten}").get_json()["data"]
    assert d["stable_gene_identifier"] == "5728"
    assert d["ncrna_relationships"][0]["ncrna"]["canonical_name"] == "hsa-mir-21"
    a = client.get(f"/api/genes/{pten}/associations").get_json()
    assert len(a["data"]["direct"]) == 1
    assert a["data"]["via_ncrna_relationships"] and "indirect" in a["notes"]
    pw = client.get(f"/api/genes/{pten}/pathways").get_json()
    assert pw["mapping_status"] == "mapped" and all(p["mapping_type"] == "direct" for p in pw["data"])
    assert client.get("/api/genes?q=mmac1").get_json()["data"][0]["approved_gene_symbol"] == "PTEN"


def test_pathway_endpoints(client, loaded):
    listing = client.get("/api/pathways?q=PI3K").get_json()
    assert listing["data"][0]["pathway_identifier"] == "hsa04151"
    pid = listing["data"][0]["id"]
    d = client.get(f"/api/pathways/{pid}").get_json()["data"]
    assert {g["approved_gene_symbol"] for g in d["genes"]} == {"PTEN", "BCL2"}
    assert d["related_associations"] and d["related_ncrnas"]
    assert client.get("/api/pathways/9999").status_code == 404


# ------------------------------------------------------------------ search
def test_global_search_and_suggest(client, loaded):
    res = client.get("/api/search?q=pten").get_json()
    assert res["data"]["genes"][0]["approved_gene_symbol"] == "PTEN"
    by_pmid = client.get("/api/search?q=17681183").get_json()["data"]
    assert by_pmid["publications"][0]["pmid"] == "17681183"
    none = client.get("/api/search?q=qqqqqq").get_json()
    assert none["total"] == 0 and all(v == [] for v in none["data"].values())
    sug = client.get("/api/search/suggest?q=hsa-mir-2").get_json()["data"]
    assert sug[0]["label"] == "hsa-mir-21"
    assert client.get("/api/search?q=a").status_code == 400
    assert client.get("/api/search?q=" + "x" * 101).status_code == 400
    assert client.get("/api/search?q=%25%25").get_json()["total"] == 0  # LIKE wildcards are escaped


# ----------------------------------------------------------------- network
def test_network_uses_only_stored_relationships(client, loaded):
    net = client.get("/api/network").get_json()["data"]
    kinds = {e["kind"] for e in net["edges"]}
    assert kinds == {"ncrna_disease", "ncrna_gene", "gene_disease"}
    gd = [e for e in net["edges"] if e["kind"] == "gene_disease"]
    assert gd and all(e["association_id"] for e in gd)
    assert len(gd) == db.session.execute(db.text("SELECT COUNT(*) FROM association_genes")).scalar()
    node_ids = {n["id"] for n in net["nodes"]}
    assert all(e["source"] in node_ids and e["target"] in node_ids for e in net["edges"])


def test_network_filters(client, loaded):
    lnc = client.get("/api/network?ncrna_type=lncRNA").get_json()["data"]
    assert all(n.get("ncrna_type") == "lncRNA" for n in lnc["nodes"] if n["kind"] == "ncrna")
    only = client.get("/api/network?include=ncrna_disease").get_json()["data"]
    assert {n["kind"] for n in only["nodes"]} == {"ncrna", "disease"}
    exp = client.get("/api/network?evidence_level=conflicting").get_json()["data"]
    assert {e["evidence_level"] for e in exp["edges"] if e["kind"] == "ncrna_disease"} == {"conflicting"}
    small = client.get("/api/network?max_associations=3").get_json()["data"]
    assert small["meta"]["associations_shown"] == 3 and small["meta"]["truncated"] is True
    pten = ids(Gene, approved_gene_symbol="PTEN")
    focus = client.get(f"/api/network?focus_type=gene&focus_id={pten}").get_json()["data"]
    assert f"gene-{pten}" in {n["id"] for n in focus["nodes"]}
    assert client.get("/api/network?include=everything").status_code == 400
    assert client.get("/api/network?focus_type=gene").status_code == 400
    assert client.get("/api/network?focus_type=gene&focus_id=9999").status_code == 404


# -------------------------------------------------------------- literature
def test_publication_served_locally_when_external_disabled(client, loaded):
    r = client.get("/api/publications/17681183").get_json()
    assert r["data"]["pmid"] == "17681183" and r["data"]["associations"]
    assert "disabled" in r["external_note"]
    missing = client.get("/api/publications/12345678")
    assert missing.status_code == 503 and missing.get_json()["error"]["code"] == "external_disabled"
    assert client.get("/api/publications/abc").status_code == 400


def test_publication_external_failure_is_reported(app, client, monkeypatch):
    app.config["EXTERNAL_LOOKUPS_ENABLED"] = True

    class Down:
        def fetch(self, pmids):
            raise ExternalServiceError("PubMed", "HTTP 503")

    monkeypatch.setattr("app.routes.literature.pubmed_service", lambda: Down())
    r = client.get("/api/publications/12345678")
    assert r.status_code == 503 and r.get_json()["error"]["code"] == "external_unavailable"


def test_publication_fetched_and_cached(app, client, monkeypatch):
    app.config["EXTERNAL_LOOKUPS_ENABLED"] = True

    class Up:
        calls = 0

        def fetch(self, pmids):
            Up.calls += 1
            return {"17681183": {"pmid": "17681183", "publication_title": "MicroRNA-21 regulates expression of the "
                                 "PTEN tumor suppressor gene in human hepatocellular cancer.",
                                 "publication_year": 2007, "journal": "Gastroenterology"}}

    monkeypatch.setattr("app.routes.literature.pubmed_service", lambda: Up())
    first = client.get("/api/publications/17681183").get_json()["data"]
    second = client.get("/api/publications/17681183").get_json()["data"]
    assert first["publication_year"] == 2007 and second["metadata_status"] == "fetched"
    assert Up.calls == 1


def test_literature_search(app, client, monkeypatch):
    assert client.get("/api/literature/search?q=miR-21").status_code == 503  # disabled in tests
    app.config["EXTERNAL_LOOKUPS_ENABLED"] = True

    class Svc:
        def search(self, q, retmax, retstart):
            return {"count": 1, "results": [{"pmid": "17681183", "publication_title": "t"}]}

    monkeypatch.setattr("app.routes.literature.pubmed_service", lambda: Svc())
    r = client.get("/api/literature/search?q=miR-21 PTEN").get_json()
    assert r["total"] == 1 and "not evidence" in r["notes"]
    assert client.get("/api/literature/search").status_code == 400


def test_rate_limiting(app, client):
    app.config["EXTERNAL_RATE_LIMIT_PER_MINUTE"] = 2
    codes = [client.get("/api/publications/abc").status_code for _ in range(3)]
    assert codes[-1] == 429


# ------------------------------------------------------------------ admin
def test_admin_requires_token(app, client):
    assert client.get("/api/admin/adapters").status_code == 401
    assert client.get("/api/admin/adapters", headers={"X-Admin-Token": "wrong"}).status_code == 401
    app.config["ADMIN_TOKEN"] = ""
    r = client.get("/api/admin/adapters", headers=ADMIN)
    assert r.status_code == 403 and r.get_json()["error"]["code"] == "admin_disabled"


def test_upload_validation(client):
    r = client.post("/api/admin/uploads", headers=ADMIN,
                    data={"file": (io.BytesIO(b"x"), "data.xlsx"), "adapter": "generic_associations"})
    assert r.status_code == 400 and "Unsupported" in r.get_json()["error"]["message"]
    r = client.post("/api/admin/uploads", headers=ADMIN,
                    data={"file": (io.BytesIO(b"a\x00b"), "data.tsv"), "adapter": "generic_associations"})
    assert r.status_code == 400
    r = client.post("/api/admin/uploads", headers=ADMIN, data={"adapter": "nope"})
    assert r.status_code == 400
    r = client.post("/api/admin/uploads", headers=ADMIN,
                    data={"file": (io.BytesIO(b"ncrna_name\tx\nA\tB\n"), "bad.tsv"), "adapter": "generic_associations"})
    body = r.get_json()["data"]
    assert r.status_code == 201 and body["valid"] is False and "Missing required" in body["preview"]["errors"][0]
    assert client.post(f"/api/admin/uploads/{body['upload_id']}/commit", headers=ADMIN, json={}).status_code == 400
    assert client.get("/api/admin/uploads/../../etc", headers=ADMIN).status_code in (400, 404)


def test_upload_preview_commit_and_report(client):
    r = client.post("/api/admin/uploads", headers=ADMIN, data={
        "file": (io.BytesIO(GENERIC_ASSOCIATIONS.encode()), "curated.tsv"), "adapter": "generic_associations",
        "source_version": "v1"})
    meta = r.get_json()["data"]
    assert r.status_code == 201 and meta["valid"]
    assert meta["preview"]["duplicates_in_file"] == 1 and meta["preview"]["unresolved"]["disease"]
    assert db.session.query(Association).count() == 0  # preview is a dry run
    c = client.post(f"/api/admin/uploads/{meta['upload_id']}/commit", headers=ADMIN,
                    json={"overrides": {"disease": {"Liver cancer of hepatocytes": "Carcinoma, Hepatocellular"}}})
    job = c.get_json()["data"]
    assert c.status_code == 201 and job["status"] == "completed" and job["records_inserted"] > 0
    assert db.session.query(Disease).filter_by(canonical_name="Liver cancer of hepatocytes").count() == 0
    again = client.post(f"/api/admin/uploads/{meta['upload_id']}/commit", headers=ADMIN, json={})
    assert again.status_code == 409
    csv_report = client.get(f"/api/admin/import-jobs/{job['id']}/report?format=csv", headers=ADMIN)
    assert csv_report.status_code == 200 and b"unresolved_rna_names" in csv_report.data
    assert client.get("/api/admin/quality-report", headers=ADMIN).get_json()["data"]["metrics"]["associations"] > 0


def test_curator_review_workflow(client, loaded):
    mir21 = ids(NcRNA, canonical_name="hsa-mir-21")
    hcc = ids(Disease, disease_identifier="D006528")
    a = db.session.query(Association).filter_by(ncrna_id=mir21, disease_id=hcc,
                                                association_type="target_mediated").one()
    t = client.post(f"/api/admin/associations/{a.id}/triage", headers=ADMIN, json={}).get_json()["data"]
    assert t["validation_status"] == "under_review"  # hints never confirm an association
    bad = client.post(f"/api/admin/associations/{a.id}/reviews", headers=ADMIN,
                      json={"outcome": "supports_direct_experimental", "pmid": "99999999", "reviewer": "x"})
    assert bad.status_code == 400  # PMID not linked to this association
    assert client.post(f"/api/admin/associations/{a.id}/reviews", headers=ADMIN,
                       json={"outcome": "great", "reviewer": "x"}).status_code == 400
    ok = client.post(f"/api/admin/associations/{a.id}/reviews", headers=ADMIN, json={
        "outcome": "supports_direct_experimental", "pmid": "17681183", "evidence_type": "direct target (abstract)",
        "reviewer": "Test Curator"})
    assert ok.status_code == 201 and ok.get_json()["data"]["validation_status"] == "curator_confirmed"
    reviews = client.get(f"/api/associations/{a.id}/reviews").get_json()
    assert reviews["validation_status"] == "curator_confirmed" and len(reviews["data"]) >= 2
    assert client.get(f"/api/associations/{a.id}").get_json()["data"]["last_verified_at"]
