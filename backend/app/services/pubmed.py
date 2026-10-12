"""PubMed / NCBI Entrez E-utilities integration.

Retrieves bibliographic metadata only. Literature retrieval is deliberately
separate from association validation: a publication that mentions an RNA and
a disease is *not* treated as evidence of an association.

Docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/
Usage policy: max 3 requests/second without an API key (10/s with a key).
"""
import re
import xml.etree.ElementTree as ET

from .http_client import ExternalServiceError, RateLimitedClient

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_URL = "https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
BATCH_SIZE = 200


def pubmed_url(pmid):
    return PUBMED_URL.format(pmid=pmid)


class PubMedService:
    def __init__(self, api_key="", email="", tool="ncRNAAtlas", timeout=15.0, client=None):
        self.api_key = api_key
        self.email = email
        self.tool = tool
        interval = 0.11 if api_key else 0.34
        self.client = client or RateLimitedClient("PubMed", min_interval=interval, timeout=timeout)

    def _params(self, **extra):
        params = {"tool": self.tool}
        if self.email:
            params["email"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key
        params.update(extra)
        return params

    def fetch(self, pmids):
        """Return ``{pmid: metadata}`` for every PMID that PubMed returns."""
        pmids = [p for p in dict.fromkeys(pmids) if p]
        results = {}
        for i in range(0, len(pmids), BATCH_SIZE):
            batch = pmids[i:i + BATCH_SIZE]
            resp = self.client.get(
                f"{EUTILS}/efetch.fcgi", params=self._params(db="pubmed", id=",".join(batch), retmode="xml")
            )
            results.update(parse_pubmed_xml(resp.content))
        return results

    def search(self, query, retmax=20, retstart=0):
        """Search PubMed. Returns ``{"count": int, "results": [summary, ...]}``."""
        resp = self.client.get(
            f"{EUTILS}/esearch.fcgi",
            params=self._params(db="pubmed", term=query, retmode="json", retmax=retmax, retstart=retstart,
                                sort="relevance"),
        )
        try:
            data = resp.json()["esearchresult"]
        except (ValueError, KeyError) as exc:
            raise ExternalServiceError("PubMed", "unexpected esearch response") from exc
        ids = data.get("idlist", [])
        count = int(data.get("count", 0))
        if not ids:
            return {"count": count, "results": []}
        resp = self.client.get(
            f"{EUTILS}/esummary.fcgi", params=self._params(db="pubmed", id=",".join(ids), retmode="json")
        )
        try:
            summary = resp.json()["result"]
        except (ValueError, KeyError) as exc:
            raise ExternalServiceError("PubMed", "unexpected esummary response") from exc
        results = []
        for pmid in ids:
            item = summary.get(pmid, {})
            year = _year(item.get("pubdate", ""))
            doi = next((a.get("value") for a in item.get("articleids", []) if a.get("idtype") == "doi"), None)
            results.append({
                "pmid": pmid,
                "publication_title": item.get("title"),
                "authors": ", ".join(a.get("name", "") for a in item.get("authors", [])[:10]) or None,
                "journal": item.get("fulljournalname") or item.get("source"),
                "publication_year": year,
                "doi": doi,
                "publication_url": pubmed_url(pmid),
            })
        return {"count": count, "results": results}


def _year(text):
    m = re.search(r"(19|20)\d{2}", text or "")
    return int(m.group(0)) if m else None


def _text(el):
    return "".join(el.itertext()).strip() if el is not None else None


def parse_pubmed_xml(content):
    """Parse an efetch PubmedArticleSet document into metadata dictionaries."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ExternalServiceError("PubMed", "malformed XML response") from exc
    out = {}
    for article in root.iter("PubmedArticle"):
        citation = article.find("MedlineCitation")
        if citation is None:
            continue
        pmid = _text(citation.find("PMID"))
        art = citation.find("Article")
        if not pmid or art is None:
            continue
        abstract_parts = []
        for part in art.findall("Abstract/AbstractText"):
            label = part.get("Label")
            text = _text(part)
            if text:
                abstract_parts.append(f"{label}: {text}" if label else text)
        authors = []
        for author in art.findall("AuthorList/Author"):
            collective = _text(author.find("CollectiveName"))
            if collective:
                authors.append(collective)
                continue
            last = _text(author.find("LastName"))
            initials = _text(author.find("Initials"))
            if last:
                authors.append(f"{last} {initials}".strip() if initials else last)
        pub_date = art.find("Journal/JournalIssue/PubDate")
        year = None
        if pub_date is not None:
            year = _year(_text(pub_date.find("Year")) or _text(pub_date.find("MedlineDate")) or "")
        doi = None
        for aid in article.findall("PubmedData/ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi":
                doi = _text(aid)
        if not doi:
            for loc in art.findall("ELocationID"):
                if loc.get("EIdType") == "doi":
                    doi = _text(loc)
        out[pmid] = {
            "pmid": pmid,
            "publication_title": _text(art.find("ArticleTitle")),
            "abstract": "\n".join(abstract_parts) or None,
            "journal": _text(art.find("Journal/Title")),
            "publication_year": year,
            "authors": ", ".join(authors) or None,
            "doi": doi,
            "publication_url": pubmed_url(pmid),
        }
    return out
