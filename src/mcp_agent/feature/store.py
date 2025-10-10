"""In-memory persistence helpers for feature intake artifacts."""

from __future__ import annotations

import json
from typing import Dict, Tuple

from .models import BudgetDecision, BudgetEstimate, FeatureDraft, FeatureSpec

ArtifactSink = Dict[str, Tuple[bytes, str]]


def _artifact_id(feature_id: str, path: str) -> str:
    return f"mem://{feature_id}/{path}"


class FeatureArtifactStore:
    def __init__(self, sink: ArtifactSink) -> None:
        self._sink = sink

    def put(self, feature_id: str, path: str, data: bytes, content_type: str) -> str:
        art_id = _artifact_id(feature_id, path)
        self._sink[art_id] = (data, content_type)
        return art_id

    def persist_spec(self, feature: FeatureDraft, spec: FeatureSpec) -> str:
        markdown = spec.as_markdown().encode("utf-8")
        return self.put(feature.feature_id, f"artifacts/feature/{feature.feature_id}/spec.md", markdown, "text/markdown")

    def persist_transcript(self, feature: FeatureDraft) -> str:
        lines = [json.dumps(message.as_dict(), sort_keys=True) for message in feature.messages]
        blob = "\n".join(lines).encode("utf-8")
        return self.put(
            feature.feature_id,
            f"artifacts/feature/{feature.feature_id}/transcript.ndjson",
            blob,
            "application/x-ndjson",
        )

    def persist_estimate(self, feature: FeatureDraft, estimate: BudgetEstimate) -> str:
        payload = json.dumps(estimate.as_dict(), sort_keys=True).encode("utf-8")
        return self.put(
            feature.feature_id,
            f"artifacts/feature/{feature.feature_id}/estimate.json",
            payload,
            "application/json",
        )

    def persist_decision(self, feature: FeatureDraft, decision: BudgetDecision) -> str:
        payload = json.dumps(decision.as_dict(), sort_keys=True).encode("utf-8")
        return self.put(
            feature.feature_id,
            f"artifacts/feature/{feature.feature_id}/decision.json",
            payload,
            "application/json",
        )


__all__ = ["FeatureArtifactStore"]
