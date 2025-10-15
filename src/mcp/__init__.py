"""Local fallback package for `mcp` providing protocol types.

When the real ``mcp`` distribution is available, this module defers to it so
that full client/server helpers continue to work.  In environments where the
package cannot be installed (for example, air-gapped CI), we ship a copy of the
protocol ``types`` module so imports like ``from mcp.types import Tool`` remain
available for tests.
"""

from __future__ import annotations

import sys
from importlib import metadata, util
from pathlib import Path

try:
    _dist = metadata.distribution("mcp")
except metadata.PackageNotFoundError:  # pragma: no cover - executed in CI fallback only
    from . import types  # noqa: F401  (re-export for local compatibility)

    __all__ = ["types"]
else:  # pragma: no cover - executed when upstream package is installed
    _origin = Path(_dist.locate_file("mcp/__init__.py"))
    _spec = util.spec_from_file_location(
        __name__,
        _origin,
        submodule_search_locations=[str(_origin.parent)],
    )
    if _spec is None or _spec.loader is None:  # pragma: no cover - safety net
        raise ImportError("Unable to load upstream mcp package")
    _module = util.module_from_spec(_spec)
    sys.modules[__name__] = _module
    _spec.loader.exec_module(_module)
    globals().update(_module.__dict__)
