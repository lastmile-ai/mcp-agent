from __future__ import annotations

import os
from typing import Dict, Iterable, Optional
from urllib.parse import urlparse

class FileLengthProvider:
    """
    Simple provider that resolves file:// URIs to local paths and returns byte lengths.
    Can be extended to consult a repo index or VCS API.
    """
    def lengths_for(self, uris: Iterable[str]) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for u in uris:
            try:
                p = self._to_local_path(u)
                if p and os.path.exists(p):
                    out[u] = max(1, os.path.getsize(p))
            except Exception:
                # ignore per-file errors
                pass
        return out

    @staticmethod
    def _to_local_path(uri: str) -> Optional[str]:
        if uri.startswith("file://"):
            parsed = urlparse(uri)
            # urlparse('file:///a/b.py') -> path '/a/b.py'
            return parsed.path
        return None
