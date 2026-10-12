"""miRNA nomenclature parsing.

ncRNAAtlas stores miRNAs at the *precursor/locus* level (e.g. ``hsa-mir-21``,
``hsa-let-7a-1``) because the association sources it imports (HMDD) report
precursor names. Mature product names (``hsa-miR-21-5p``) are parsed to their
precursor stem and recorded as aliases when the mapping is unambiguous.
"""
import re
from dataclasses import dataclass

SPECIES_PREFIX = {"Homo sapiens": "hsa", "Mus musculus": "mmu", "Rattus norvegicus": "rno"}

_NAME = re.compile(r"^(?:(?P<species>[a-z]{3,4})-)?(?P<kind>mir|let|lin)-(?P<body>.+)$", re.IGNORECASE)
_BODY = re.compile(
    r"^(?P<core>\d+[a-z]?)(?:-(?P<locus>\d+))?(?:-(?P<arm>[35]p)|(?P<star>\*))?$", re.IGNORECASE
)


@dataclass(frozen=True)
class ParsedMiRNA:
    species: str
    kind: str  # mir | let | lin
    core: str  # e.g. "21", "125b", "7a"
    locus: str | None
    arm: str | None  # 5p | 3p | * | None
    is_mature: bool

    @property
    def precursor_name(self):
        name = f"{self.species}-{self.kind}-{self.core}"
        return f"{name}-{self.locus}" if self.locus else name

    @property
    def hgnc_symbol(self):
        """HGNC symbol for a human precursor locus (``MIR21``, ``MIR125B1``, ``MIRLET7A1``, ``MIR1-1``)."""
        base = ("MIRLET" if self.kind == "let" else "MIR") + self.core.upper()
        if not self.locus:
            return base
        return f"{base}-{self.locus}" if base[-1].isdigit() else f"{base}{self.locus}"

    @property
    def hgnc_base(self):
        return ("MIRLET" if self.kind == "let" else "MIR") + self.core.upper()


def parse_mirna(name, organism="Homo sapiens"):
    """Parse a miRNA name. Returns ``None`` when the name is not miRBase-style."""
    if not name:
        return None
    m = _NAME.match(name.strip())
    if not m:
        return None
    body = _BODY.match(m.group("body"))
    if not body:
        return None
    raw_kind = m.group("kind")
    species = (m.group("species") or SPECIES_PREFIX.get(organism, "hsa")).lower()
    arm = body.group("arm") or body.group("star")
    # miRBase convention: "miR" (capital R) denotes a mature product.
    is_mature = bool(arm) or raw_kind == "miR"
    return ParsedMiRNA(
        species=species,
        kind=raw_kind.lower(),
        core=body.group("core").lower(),
        locus=body.group("locus"),
        arm=arm.lower() if arm else None,
        is_mature=is_mature,
    )


def looks_like_mirna(name):
    return parse_mirna(name) is not None
