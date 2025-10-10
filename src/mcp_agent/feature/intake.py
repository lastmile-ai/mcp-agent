"""Feature intake orchestration utilities."""

from __future__ import annotations

import uuid
from typing import Callable, Dict, Optional

from mcp_agent.runloop.events import EventBus

from .estimator import estimate_budget
from .events import (
    emit_awaiting_confirmation,
    emit_budget_confirmed,
    emit_cancelled,
    emit_drafting,
    emit_estimated,
)
from .models import BudgetDecision, BudgetEstimate, FeatureDraft, FeatureMessage, FeatureSpec, FeatureState, MessageRole
from .store import FeatureArtifactStore

EstimatorFn = Callable[[FeatureSpec], BudgetEstimate]


class FeatureIntakeManager:
    """In-memory manager that drives the feature-intake lifecycle."""

    def __init__(
        self,
        *,
        artifact_sink: Dict[str, tuple[bytes, str]],
        estimator: EstimatorFn | None = None,
    ) -> None:
        self._features: Dict[str, FeatureDraft] = {}
        self._buses: Dict[str, EventBus] = {}
        self._artifact_store = FeatureArtifactStore(artifact_sink)
        self._estimator = estimator or estimate_budget

    def create(
        self,
        *,
        project_id: str,
        trace_id: Optional[str] = None,
    ) -> FeatureDraft:
        feature_id = str(uuid.uuid4())
        draft = FeatureDraft(feature_id=feature_id, project_id=project_id, trace_id=trace_id or feature_id)
        self._features[feature_id] = draft
        self._buses[feature_id] = EventBus()
        return draft

    def get(self, feature_id: str) -> FeatureDraft | None:
        return self._features.get(feature_id)

    def bus(self, feature_id: str) -> EventBus:
        return self._buses.setdefault(feature_id, EventBus())

    async def append_message(self, feature_id: str, role: MessageRole, content: str) -> FeatureDraft:
        draft = self._require(feature_id)
        if draft.state in {FeatureState.CANCELLED, FeatureState.CONFIRMED}:
            raise RuntimeError("cannot_modify_finalized_feature")
        message = FeatureMessage(role=role, content=content)
        draft.append(message)
        await emit_drafting(self.bus(feature_id), draft)
        return draft

    async def freeze_spec(self, feature_id: str, payload: dict) -> FeatureDraft:
        draft = self._require(feature_id)
        spec = FeatureSpec.from_dict(payload)
        draft.set_spec(spec)
        self._artifact_store.persist_spec(draft, spec)
        self._artifact_store.persist_transcript(draft)
        return draft

    async def estimate(self, feature_id: str) -> FeatureDraft:
        draft = self._require(feature_id)
        if draft.spec is None:
            raise RuntimeError("spec_missing")
        estimate = self._estimator(draft.spec)
        draft.set_estimate(estimate)
        draft.set_state(FeatureState.ESTIMATED)
        self._artifact_store.persist_estimate(draft, estimate)
        await emit_estimated(self.bus(feature_id), draft)
        draft.set_state(FeatureState.AWAITING_CONFIRMATION)
        await emit_awaiting_confirmation(self.bus(feature_id), draft)
        return draft

    async def confirm(self, feature_id: str, *, seconds: Optional[int] = None, rationale: str | None = None) -> FeatureDraft:
        draft = self._require(feature_id)
        if draft.estimate is None:
            raise RuntimeError("estimate_missing")
        approved_seconds = int(seconds if seconds is not None else draft.estimate.seconds)
        decision = BudgetDecision(seconds=approved_seconds, approved=True, rationale=rationale)
        draft.set_decision(decision)
        draft.set_state(FeatureState.CONFIRMED)
        self._artifact_store.persist_decision(draft, decision)
        await emit_budget_confirmed(self.bus(feature_id), draft)
        return draft

    async def cancel(self, feature_id: str) -> FeatureDraft:
        draft = self._require(feature_id)
        draft.cancel()
        await emit_cancelled(self.bus(feature_id), draft)
        return draft

    async def close(self) -> None:
        for bus in self._buses.values():
            await bus.close()
        self._buses.clear()

    def reset(self) -> None:
        self._features.clear()
        self._buses.clear()

    def _require(self, feature_id: str) -> FeatureDraft:
        if feature_id not in self._features:
            raise KeyError("feature_not_found")
        return self._features[feature_id]


__all__ = ["FeatureIntakeManager"]
