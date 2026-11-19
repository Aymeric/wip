"""
Dynamic delegating proxy for accessing engine utilities and constants.
Eliminates circular import cycles between src.gex.cli modules and src.gex_engine
while preserving dynamic runtime attribute lookups and mock patching fidelity.
"""

import sys
from typing import Any


class _GeProxy:
    def __getattr__(self, name: str) -> Any:
        mod = sys.modules.get("src.gex_engine") or sys.modules.get("gex_engine")
        if mod is None:
            import src.gex_engine as m
            return getattr(m, name)
        return getattr(mod, name)


ge = _GeProxy()
