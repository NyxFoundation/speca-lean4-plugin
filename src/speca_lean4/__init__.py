"""speca-lean4-plugin — gasper-lean4 (Lean 4) -> SPECA `01e` property provider.

External, version-pinned plugin resolved by speca's `lean` property provider
(speca#87 seam). Public API:

    from speca_lean4 import build_properties, load_health, validate_property
"""

from .health import index_health, load_health, status_for
from .mapping import build_properties, build_property
from .schema import Property, Reachability, validate_property

__all__ = [
    "build_properties",
    "build_property",
    "index_health",
    "load_health",
    "status_for",
    "Property",
    "Reachability",
    "validate_property",
]

__version__ = "0.1.0"
