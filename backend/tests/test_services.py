"""External service clients, with all network access mocked."""
import pytest
import requests

from app.ingestion.enrichment import map_kegg_pathways
from app.services.http_client import ExternalServiceError, RateLimitedClient
from app.services.kegg import KEGGService, parse_link, parse_pathway_list
from app.services.pubmed import PubMedService, parse_pubmed_xml
from conftest import FIXTURES


class FakeResponse:
    def __init__(self, status=200, text="", content=None, json_data=None):
        self.status_code = status
        self.text = text
        self.content = content if content is not None else text.encode()
        self._json = json_data

    def json(self):
        return self._json


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, accept_404=False):
        self.calls.append((url, params))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_parse_pubmed_xml_extracts_metadata():
    data = parse_pubmed_xml((FIXTURES / "pubmed_efetch.xml").read_bytes())
    meng = data["17681183"]
    assert meng["publication_title"].startswith("MicroRNA-21 regulates expression of the PTEN")
    assert meng["publication_year"] == 2007
    assert meng["journal"] and meng["authors"].startswith("Meng")
    assert meng["doi"] and meng["abstract"]
    assert data["16166262"]["publication_year"] == 2005


def test_parse_pubmed_xml_rejects_malformed():
    with pytest.raises(ExternalServiceError):
        parse_pubmed_xml(b"<not-xml")


def test_pubmed_fetch_uses_mocked_client():
    client = FakeClient([FakeResponse(content=(FIXTURES / "pubmed_efetch.xml").read_bytes())])
    svc = PubMedService(client=client)
    out = svc.fetch(["17681183", "16166262", "17681183"])
    assert set(out) == {"17681183", "16166262"}
    assert client.calls[0][1]["id"] == "17681183,16166262"


def test_pubmed_search_parses_esearch_and_esummary():
    client = FakeClient([
        FakeResponse(json_data={"esearchresult": {"count": "1", "idlist": ["17681183"]}}),
        FakeResponse(json_data={"result": {"17681183": {
            "title": "MicroRNA-21 regulates expression of the PTEN tumor suppressor gene in human hepatocellular cancer.",
            "pubdate": "2007 Aug", "fulljournalname": "Gastroenterology", "authors": [{"name": "Meng F"}],
            "articleids": [{"idtype": "doi", "value": "10.1053/j.gastro.2007.05.022"}]}}}),
    ])
    res = PubMedService(client=client).search("miR-21 PTEN")
    assert res["count"] == 1 and res["results"][0]["publication_year"] == 2007


def test_mesh_descriptor_then_entry_term_resolution():
    from app.services.mesh import MeSHService

    exact = FakeResponse(json_data=[{"resource": "http://id.nlm.nih.gov/mesh/D001943", "label": "Breast Neoplasms"}])
    assert MeSHService(client=FakeClient([exact])).lookup_descriptor("breast neoplasms")["id"] == "D001943"

    via_term = FakeClient([
        FakeResponse(json_data=[]),  # no descriptor with this label
        FakeResponse(json_data=[{"resource": "http://id.nlm.nih.gov/mesh/T001150132", "label": "Carcinoma, Basal Cell"}]),
        FakeResponse(json_data={"results": {"bindings": [{"d": {"value": "http://id.nlm.nih.gov/mesh/D002280"},
                                                         "dName": {"value": "Basal Cell Carcinoma"}}]}}),
    ])
    hit = MeSHService(client=via_term).lookup_descriptor("Carcinoma, Basal Cell")
    assert hit == {"id": "D002280", "label": "Basal Cell Carcinoma", "matched_via": "entry_term",
                   "entry_term": "Carcinoma, Basal Cell"}


def test_mesh_rejects_terms_shared_by_several_descriptors():
    from app.services.mesh import MeSHService

    client = FakeClient([
        FakeResponse(json_data=[]),
        FakeResponse(json_data=[{"resource": "http://id.nlm.nih.gov/mesh/T1", "label": "Shared Term"}]),
        FakeResponse(json_data={"results": {"bindings": [
            {"d": {"value": "http://id.nlm.nih.gov/mesh/D1"}, "dName": {"value": "A"}},
            {"d": {"value": "http://id.nlm.nih.gov/mesh/D2"}, "dName": {"value": "B"}}]}}),
    ])
    assert MeSHService(client=client).lookup_descriptor("Shared Term") is None
    assert MeSHService(client=FakeClient([FakeResponse(json_data=[]), FakeResponse(json_data=[])])) \
        .lookup_descriptor("Liver cancer of hepatocytes") is None


def test_kegg_parsers():
    links = parse_link((FIXTURES / "kegg_link.txt").read_text())
    assert "hsa04151" in links["5728"] and "hsa04151" in links["596"]
    names = parse_pathway_list((FIXTURES / "kegg_list.txt").read_text())
    assert names["hsa04151"] == "PI3K-Akt signaling pathway"


def test_rate_limited_client_raises_on_network_failure(monkeypatch):
    client = RateLimitedClient("Test", min_interval=0, retries=1)
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise requests.ConnectionError("down")

    monkeypatch.setattr(client.session, "get", boom)
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(ExternalServiceError) as exc:
        client.get("https://example.invalid")
    assert exc.value.service == "Test" and len(calls) == 2


def test_rate_limited_client_does_not_retry_client_errors(monkeypatch):
    client = RateLimitedClient("Test", min_interval=0, retries=3)
    calls = []
    monkeypatch.setattr(client.session, "get", lambda *a, **k: calls.append(1) or FakeResponse(status=400))
    with pytest.raises(ExternalServiceError) as exc:
        client.get("https://example.invalid")
    assert exc.value.status_code == 400 and len(calls) == 1


def _genes(app):
    from app.extensions import db
    from app.models import Gene

    db.session.add_all([
        Gene(approved_gene_symbol="PTEN", stable_gene_identifier="5728", identifier_namespace="NCBIGene"),
        Gene(approved_gene_symbol="BCL2", stable_gene_identifier="596", identifier_namespace="NCBIGene"),
        Gene(approved_gene_symbol="NOID1"),  # no reliable identifier -> never mapped
    ])
    db.session.commit()


def test_kegg_mapping_live_mocked(app):
    _genes(app)
    client = FakeClient([FakeResponse(text=(FIXTURES / "kegg_list.txt").read_text()),
                         FakeResponse(text=(FIXTURES / "kegg_link.txt").read_text())])
    report = map_kegg_pathways(KEGGService(client=client))
    assert report["mode"] == "live" and report["genes_considered"] == 2 and report["genes_mapped"] == 2
    from app.models import Pathway

    assert Pathway.query.filter_by(pathway_identifier="hsa04151").one().pathway_name == "PI3K-Akt signaling pathway"


def test_kegg_mapping_falls_back_to_cache_when_unavailable(app):
    _genes(app)
    client = FakeClient([ExternalServiceError("KEGG", "HTTP 503")])
    cache = {"retrieved_at": "test", "links": parse_link((FIXTURES / "kegg_link.txt").read_text()),
             "pathway_names": {}}
    report = map_kegg_pathways(KEGGService(client=client), cache)
    assert report["mode"] == "cache" and report["genes_mapped"] == 2 and report["errors"]


def test_kegg_mapping_reports_failure_without_cache(app):
    _genes(app)
    report = map_kegg_pathways(KEGGService(client=FakeClient([ExternalServiceError("KEGG", "timeout")])))
    assert report["mode"] == "failed" and report["links_created"] == 0
