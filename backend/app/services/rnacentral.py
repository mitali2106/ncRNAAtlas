"""RNAcentral REST API integration (RNA identity and sequences).

Docs: https://rnacentral.org/api. RNAcentral entries describe RNA identity
and sequence; they are never treated as evidence of a disease association.
"""
from .http_client import RateLimitedClient

RNACENTRAL_API = "https://rnacentral.org/api/v1"
RNACENTRAL_URL = "https://rnacentral.org/rna/{urs}"


def rnacentral_url(urs):
    return RNACENTRAL_URL.format(urs=urs)


class RNAcentralService:
    def __init__(self, timeout=15.0, client=None):
        self.client = client or RateLimitedClient("RNAcentral", min_interval=0.25, timeout=timeout)

    def get_sequence(self, urs_id):
        """Return ``{"rnacentral_id", "sequence", "length", "description"}`` or ``None``."""
        urs = urs_id.split("_", 1)[0]
        resp = self.client.get(f"{RNACENTRAL_API}/rna/{urs}", params={"format": "json"}, accept_404=True)
        if resp.status_code == 404:
            return None
        data = resp.json()
        return {
            "rnacentral_id": data.get("rnacentral_id", urs),
            "sequence": data.get("sequence"),
            "length": data.get("length"),
            "description": data.get("description"),
        }

    def search_external_id(self, external_id):
        """Return RNAcentral entries cross-referenced to an external ID (e.g. a miRBase accession)."""
        resp = self.client.get(f"{RNACENTRAL_API}/rna/", params={"external_id": external_id, "format": "json"})
        return [
            {"rnacentral_id": r.get("rnacentral_id"), "length": r.get("length"), "sequence": r.get("sequence")}
            for r in resp.json().get("results", [])
        ]
