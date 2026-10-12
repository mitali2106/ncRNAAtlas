"""KEGG REST API integration (gene-to-pathway mapping for human genes).

Docs: https://www.kegg.jp/kegg/rest/keggapi.html
KEGG REST is provided for academic use; see https://www.kegg.jp/kegg/legal.html.
Genes are mapped via their NCBI Gene (Entrez) identifier, which is KEGG's
human gene identifier (``hsa:<entrez_id>``). Genes without a reliable Entrez
identifier are never mapped.
"""
from .http_client import RateLimitedClient

KEGG_REST = "https://rest.kegg.jp"
PATHWAY_URL = "https://www.kegg.jp/pathway/{pid}"
LINK_BATCH = 10


def pathway_url(pathway_id):
    return PATHWAY_URL.format(pid=pathway_id)


def _strip_prefix(value):
    return value.split(":", 1)[1] if ":" in value else value


class KEGGService:
    def __init__(self, timeout=15.0, client=None):
        # KEGG asks users to keep request rates modest; ~3 req/s is used here.
        self.client = client or RateLimitedClient("KEGG", min_interval=0.4, timeout=timeout)

    def list_human_pathways(self):
        """``{pathway_id: name}`` for all human pathways (``hsa04010`` → ``MAPK signaling pathway``)."""
        resp = self.client.get(f"{KEGG_REST}/list/pathway/hsa")
        return parse_pathway_list(resp.text)

    def link_genes(self, entrez_ids):
        """``{entrez_id: [pathway_id, ...]}`` for the given human gene IDs."""
        ids = [str(i) for i in dict.fromkeys(entrez_ids) if i]
        out = {i: [] for i in ids}
        for start in range(0, len(ids), LINK_BATCH):
            batch = ids[start:start + LINK_BATCH]
            resp = self.client.get(
                f"{KEGG_REST}/link/pathway/" + "+".join(f"hsa:{i}" for i in batch), accept_404=True
            )
            if resp.status_code == 404:
                continue
            for gene, pathways in parse_link(resp.text).items():
                out.setdefault(gene, []).extend(pathways)
        return out


def parse_pathway_list(text):
    out = {}
    for line in text.splitlines():
        if "\t" not in line:
            continue
        pid, name = line.split("\t", 1)
        pid = _strip_prefix(pid.strip())
        name = name.strip()
        suffix = " - Homo sapiens (human)"
        if name.endswith(suffix):
            name = name[: -len(suffix)]
        out[pid] = name
    return out


def parse_link(text):
    out = {}
    for line in text.splitlines():
        parts = line.strip().split("\t")
        if len(parts) != 2:
            continue
        gene, pathway = _strip_prefix(parts[0]), _strip_prefix(parts[1])
        out.setdefault(gene, [])
        if pathway not in out[gene]:
            out[gene].append(pathway)
    return out
