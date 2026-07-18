"""speca-lean4-plugin — gasper-lean4 (Lean 4) -> SPECA `01e` property provider.

External, version-pinned plugin resolved by speca's `lean` property provider
(speca#87 seam). Public API:

    from speca_lean4 import build_properties, load_health, validate_property
"""

from .health import index_health, load_health, status_for, health_for
from .mapping import (
    build_properties,
    build_properties_by_shard,
    build_property,
    derive_severities,
    lower_entry,
)
from .schema import Property, Reachability, validate_property
from .kurtosis import (
    attach_checkers,
    emit_kurtosis,
    load_checker_map,
    load_evidence_seeds,
)

__all__ = [
    "build_properties",
    "build_properties_by_shard",
    "build_property",
    "derive_severities",
    "lower_entry",
    "index_health",
    "load_health",
    "status_for",
    "health_for",
    "Property",
    "Reachability",
    "validate_property",
    "attach_checkers",
    "emit_kurtosis",
    "load_checker_map",
    "load_evidence_seeds",
]

__version__ = "0.1.0"
