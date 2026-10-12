"""HGNC complete-set loader (gene, lncRNA and miRNA-locus nomenclature).

Source: https://www.genenames.org/download/ (CC0). ncRNAAtlas uses the
tab-separated "complete set" file, or the small subset bundled with the
sample dataset. Only rows with status ``Approved`` are indexed.
"""
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

HGNC_DOWNLOAD_URL = "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt"
HGNC_COLUMNS = [
    "hgnc_id", "symbol", "name", "locus_group", "locus_type", "status", "alias_symbol",
    "prev_symbol", "entrez_id", "ensembl_gene_id", "mirbase", "rna_central_id",
]


def _multi(value):
    if not value:
        return []
    return [v.strip().strip('"') for v in value.split("|") if v.strip().strip('"')]


@dataclass
class HGNCRecord:
    hgnc_id: str
    symbol: str
    name: str
    locus_group: str
    locus_type: str
    alias_symbols: list = field(default_factory=list)
    prev_symbols: list = field(default_factory=list)
    entrez_id: str | None = None
    ensembl_gene_id: str | None = None
    mirbase: str | None = None
    rna_central_ids: list = field(default_factory=list)

    @property
    def is_noncoding(self):
        return self.locus_group in ("non-coding RNA", "pseudogene")

    @property
    def is_mirna(self):
        return self.locus_type == "RNA, micro"


class HGNCIndex:
    def __init__(self, records=()):
        self.by_symbol, self.by_prev, self.by_alias, self.by_entrez, self.by_mirbase = {}, {}, {}, {}, {}
        self.mirna_symbols = []
        for rec in records:
            self.add(rec)

    def __len__(self):
        return len(self.by_symbol)

    def add(self, rec):
        self.by_symbol[rec.symbol.upper()] = rec
        for s in rec.prev_symbols:
            self.by_prev.setdefault(s.upper(), []).append(rec)
        for s in rec.alias_symbols:
            self.by_alias.setdefault(s.upper(), []).append(rec)
        if rec.entrez_id:
            self.by_entrez[rec.entrez_id] = rec
        if rec.mirbase:
            self.by_mirbase[rec.mirbase] = rec
        if rec.is_mirna:
            self.mirna_symbols.append(rec.symbol.upper())

    @classmethod
    def from_file(cls, path):
        records = []
        with Path(path).open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                if (row.get("status") or "Approved") != "Approved":
                    continue
                records.append(
                    HGNCRecord(
                        hgnc_id=row["hgnc_id"],
                        symbol=row["symbol"],
                        name=row.get("name") or "",
                        locus_group=row.get("locus_group") or "",
                        locus_type=row.get("locus_type") or "",
                        alias_symbols=_multi(row.get("alias_symbol")),
                        prev_symbols=_multi(row.get("prev_symbol")),
                        entrez_id=(row.get("entrez_id") or "").strip() or None,
                        ensembl_gene_id=(row.get("ensembl_gene_id") or "").strip() or None,
                        mirbase=(row.get("mirbase") or "").strip() or None,
                        rna_central_ids=_multi(row.get("rna_central_id")),
                    )
                )
        return cls(records)

    def lookup(self, symbol):
        """Resolve a symbol. Returns ``(record_or_None, method, candidates)``.

        Precedence: approved symbol > unique previous symbol > unique alias.
        Ambiguous previous/alias symbols are *not* resolved.
        """
        key = (symbol or "").strip().upper()
        if not key:
            return None, None, []
        if key in self.by_symbol:
            return self.by_symbol[key], "approved_symbol", []
        prev = self.by_prev.get(key, [])
        if len(prev) == 1:
            return prev[0], "previous_symbol", []
        if len(prev) > 1:
            return None, "ambiguous_previous_symbol", prev
        alias = self.by_alias.get(key, [])
        if len(alias) == 1:
            return alias[0], "alias_symbol", []
        if len(alias) > 1:
            return None, "ambiguous_alias_symbol", alias
        return None, None, []

    def mirna_loci(self, base_symbol):
        """All miRNA locus symbols for a stem, e.g. ``MIR16`` -> ``MIR16-1``, ``MIR16-2``."""
        # A digit-final stem takes a hyphenated locus (MIR1 -> MIR1-1, never MIR100);
        # a letter-final stem takes a bare one (MIR125B -> MIR125B1).
        suffix = r"(-\d+)?" if base_symbol[-1:].isdigit() else r"(\d+)?"
        pattern = re.compile(rf"^{re.escape(base_symbol)}{suffix}$")
        return sorted(s for s in self.mirna_symbols if pattern.match(s))

    def write_subset(self, path, symbols):
        """Write an HGNC-format subset file containing only ``symbols`` (for the sample dataset)."""
        wanted = [self.by_symbol[s.upper()] for s in sorted(set(symbols)) if s.upper() in self.by_symbol]
        with Path(path).open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
            writer.writerow(HGNC_COLUMNS)
            for r in wanted:
                writer.writerow([
                    r.hgnc_id, r.symbol, r.name, r.locus_group, r.locus_type, "Approved",
                    "|".join(r.alias_symbols), "|".join(r.prev_symbols), r.entrez_id or "",
                    r.ensembl_gene_id or "", r.mirbase or "", "|".join(r.rna_central_ids),
                ])
        return len(wanted)
