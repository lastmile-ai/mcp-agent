from __future__ import annotations

import asyncio
from typing import Optional

from .toolkit import AggregatorToolKit
from .telemetry import meter


async def verify_hmac_once(trace_id: Optional[str] = None) -> bool:
    """
    Attempt a cheap patterns() call using the registry and report success via metrics.
    Returns True on 200-class response with no auth error, else False.
    No exception propagation.
    """
    m = meter()
    try:
        tk = AggregatorToolKit(trace_id=trace_id)
        # A benign call. If a tool exists with 'patterns' capability it should accept an empty list.
        res = await asyncio.wait_for(tk.patterns([]), timeout=1.0)
        ok = isinstance(res, list)
        m.record_duration_ms(0.0, {"phase":"assemble","probe":"hmac","ok":str(ok)})
        return ok
    except Exception:
        m.record_duration_ms(0.0, {"phase":"assemble","probe":"hmac","ok":"False"})
        return False
