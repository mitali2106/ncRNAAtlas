"""Interaction-network endpoint."""
from flask import Blueprint, request

from ..api_utils import APIError, get_choice, get_int, get_str, ok
from ..extensions import db
from ..models import Disease, Gene, NcRNA
from ..models.constants import EVIDENCE_LEVELS, HUMAN, NCRNA_TYPES
from ..services.network import DEFAULT_EDGES, EDGE_KINDS, MAX_EDGES, build_network

bp = Blueprint("network", __name__)
FOCUS_MODELS = {"ncrna": NcRNA, "disease": Disease, "gene": Gene}


def _list(name, allowed):
    values = [v.strip() for v in (request.args.get(name) or "").split(",") if v.strip()]
    bad = [v for v in values if v not in allowed]
    if bad:
        raise APIError(400, f"Invalid {name}: {', '.join(bad)}. Allowed: {', '.join(allowed)}")
    return values


@bp.get("/network")
def network():
    focus_type = get_choice("focus_type", set(FOCUS_MODELS))
    focus_id = get_int("focus_id", minimum=1)
    if bool(focus_type) != bool(focus_id):
        raise APIError(400, "focus_type and focus_id must be supplied together")
    if focus_type and db.session.get(FOCUS_MODELS[focus_type], focus_id) is None:
        raise APIError(404, f"{focus_type} {focus_id} not found")
    include = _list("include", EDGE_KINDS) or list(EDGE_KINDS)
    data = build_network(
        focus_type=focus_type, focus_id=focus_id,
        ncrna_types=_list("ncrna_type", NCRNA_TYPES),
        evidence_levels=_list("evidence_level", list(EVIDENCE_LEVELS)),
        include=include,
        max_associations=get_int("max_associations", DEFAULT_EDGES, 1, MAX_EDGES),
        organism=get_str("organism", HUMAN),
    )
    return ok(data)
