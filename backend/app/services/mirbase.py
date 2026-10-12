"""miRBase flat-file parser.

miRBase (https://www.mirbase.org) distributes ``miRNA.dat`` (EMBL format)
with precursor accessions, sequences and mature products. Its website was not
reachable from the development environment, so ncRNAAtlas reads a locally
downloaded ``miRNA.dat`` file (``import_data.py mirbase --path ...``) rather
than calling a live API. When no file is available, miRNA identities are
resolved through HGNC (which records miRBase accessions) and sequences through
RNAcentral.
"""
import re
from pathlib import Path

MIRBASE_URL = "https://www.mirbase.org/hairpin/{acc}"
MATURE_URL = "https://www.mirbase.org/mature/{acc}"


def mirbase_url(accession):
    return MIRBASE_URL.format(acc=accession)


def parse_mirna_dat(path_or_text):
    """Yield one dict per precursor entry in an EMBL-format ``miRNA.dat``."""
    if isinstance(path_or_text, (str, Path)) and Path(str(path_or_text)).exists():
        text = Path(path_or_text).read_text(encoding="utf-8", errors="replace")
    else:
        text = str(path_or_text)
    for block in text.split("\n//"):
        lines = [ln.rstrip("\r") for ln in block.strip("\n").splitlines()]
        if not lines:
            continue
        entry = {"id": None, "accession": None, "description": None, "sequence": "", "products": []}
        in_seq = False
        current = None
        for ln in lines:
            tag = ln[:2]
            body = ln[5:] if len(ln) > 5 else ""
            if tag == "ID":
                entry["id"] = body.split()[0]
            elif tag == "AC":
                entry["accession"] = body.strip().rstrip(";")
            elif tag == "DE":
                entry["description"] = ((entry["description"] or "") + " " + body.strip()).strip()
            elif tag == "SQ":
                in_seq = True
            elif tag == "FT":
                m = re.match(r"FT\s+miRNA\s+(\d+)\.\.(\d+)", ln)
                if m:
                    current = {"start": int(m.group(1)), "end": int(m.group(2)), "accession": None, "name": None}
                    entry["products"].append(current)
                    continue
                q = re.search(r'/(accession|product)="([^"]+)"', ln)
                if q and current is not None:
                    current["name" if q.group(1) == "product" else "accession"] = q.group(2)
            elif in_seq and ln.startswith("     "):
                entry["sequence"] += re.sub(r"[^A-Za-z]", "", ln)
        if not entry["id"]:
            continue
        seq = entry["sequence"].upper().replace("T", "U")
        entry["sequence"] = seq
        for p in entry["products"]:
            p["sequence"] = seq[p["start"] - 1:p["end"]] if seq else None
        yield entry
