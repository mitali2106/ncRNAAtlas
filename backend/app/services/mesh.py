"""NLM MeSH lookup (disease identifier resolution).

Resolution is exact-match only, in two steps:

1. **Descriptor label**: the name equals a MeSH descriptor heading.
2. **Synonym entry term**: the name equals a MeSH *term* of the **preferred
   concept** of exactly one topical descriptor, i.e. a true synonym. This is
   needed because NLM has re-worded many headings ("Carcinoma, Basal Cell" is
   now a synonym in descriptor D002280 "Basal Cell Carcinoma") while source
   databases still use the older headings.

Terms of *narrower or related* concepts are deliberately not accepted: MeSH
files e.g. "laryngeal squamous cell carcinoma" under "Squamous Cell Carcinoma
of Head and Neck", and merging it there would erase specificity. No partial or
fuzzy matching is ever used; such names stay unresolved.

APIs: https://id.nlm.nih.gov/mesh/ (lookup service and SPARQL endpoint).
"""
from .http_client import ExternalServiceError, RateLimitedClient

MESH_BASE = "https://id.nlm.nih.gov/mesh"
MESH_BROWSER_URL = "https://meshb.nlm.nih.gov/record/ui?ui={ui}"

_TERM_TO_DESCRIPTOR = """PREFIX meshv: <http://id.nlm.nih.gov/mesh/vocab#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?d ?dName FROM <http://id.nlm.nih.gov/mesh> WHERE {
  VALUES ?t { %s }
  ?c (meshv:term|meshv:preferredTerm) ?t .
  ?d meshv:preferredConcept ?c ; a meshv:TopicalDescriptor ; rdfs:label ?dName .
}"""


def mesh_url(ui):
    return MESH_BROWSER_URL.format(ui=ui)


def _ui(uri):
    return uri.rstrip("/").rsplit("/", 1)[-1]


class MeSHService:
    def __init__(self, timeout=15.0, client=None):
        self.client = client or RateLimitedClient("MeSH", min_interval=0.2, timeout=timeout)

    def _exact(self, kind, label):
        resp = self.client.get(f"{MESH_BASE}/lookup/{kind}", params={"label": label, "match": "exact", "limit": 5})
        try:
            results = resp.json()
        except ValueError as exc:
            raise ExternalServiceError("MeSH", "unexpected lookup response") from exc
        return [r for r in results if r.get("label", "").lower() == label.lower()]

    def lookup_descriptor(self, label):
        """Return ``{"id", "label", "matched_via"[, "entry_term"]}`` for an exact match, else ``None``."""
        descriptors = self._exact("descriptor", label)
        if len(descriptors) == 1:
            return {"id": _ui(descriptors[0]["resource"]), "label": descriptors[0]["label"],
                    "matched_via": "descriptor_label"}
        if len(descriptors) > 1:
            return None
        terms = self._exact("term", label)
        if not terms:
            return None
        values = " ".join(f"<{t['resource']}>" for t in terms)
        resp = self.client.get(f"{MESH_BASE}/sparql", params={"query": _TERM_TO_DESCRIPTOR % values, "format": "JSON"})
        try:
            bindings = resp.json()["results"]["bindings"]
        except (ValueError, KeyError) as exc:
            raise ExternalServiceError("MeSH", "unexpected SPARQL response") from exc
        found = {(_ui(b["d"]["value"]), b["dName"]["value"]) for b in bindings}
        if len(found) != 1:
            return None
        ui, name = found.pop()
        return {"id": ui, "label": name, "matched_via": "entry_term", "entry_term": terms[0]["label"]}
