"""In-memory workflow composition manager used by the admin API."""

from __future__ import annotations

import asyncio
from typing import Dict, Iterable, Optional

from mcp_agent.models.workflow import (
    WorkflowDefinition,
    WorkflowPatch,
    WorkflowStep,
    WorkflowStepPatch,
    WorkflowSummary,
)


class WorkflowComposerError(RuntimeError):
    pass


class WorkflowNotFoundError(WorkflowComposerError):
    pass


class WorkflowComposer:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._definitions: Dict[str, WorkflowDefinition] = {}

    async def clear(self) -> None:
        async with self._lock:
            self._definitions.clear()

    async def list(self) -> list[WorkflowSummary]:
        async with self._lock:
            return [
                WorkflowSummary(
                    id=definition.id,
                    name=definition.name,
                    description=definition.description,
                    updated_at=definition.updated_at,
                    step_count=_count_steps(definition.root),
                )
                for definition in self._definitions.values()
            ]

    async def get(self, workflow_id: str) -> WorkflowDefinition:
        async with self._lock:
            definition = self._definitions.get(workflow_id)
            if definition is None:
                raise WorkflowNotFoundError(workflow_id)
            return definition

    async def create(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        async with self._lock:
            if definition.id in self._definitions:
                raise WorkflowComposerError(f"workflow '{definition.id}' already exists")
            self._definitions[definition.id] = definition
            return definition

    async def delete(self, workflow_id: str) -> None:
        async with self._lock:
            if workflow_id not in self._definitions:
                raise WorkflowNotFoundError(workflow_id)
            del self._definitions[workflow_id]

    async def update(self, workflow_id: str, patch: WorkflowPatch) -> WorkflowDefinition:
        async with self._lock:
            definition = self._definitions.get(workflow_id)
            if definition is None:
                raise WorkflowNotFoundError(workflow_id)
            data = definition.model_dump()
            if patch.name is not None:
                data["name"] = patch.name
            if patch.description is not None:
                data["description"] = patch.description
            if patch.metadata is not None:
                data["metadata"] = patch.metadata
            definition = WorkflowDefinition(**data)
            self._definitions[workflow_id] = definition
            return definition

    async def patch_step(
        self, workflow_id: str, step_id: str, patch: WorkflowStepPatch
    ) -> WorkflowDefinition:
        async with self._lock:
            definition = self._definitions.get(workflow_id)
            if definition is None:
                raise WorkflowNotFoundError(workflow_id)
            replaced_root = _patch_step(definition.root, step_id, patch)
            definition = definition.model_copy(update={"root": replaced_root})
            self._definitions[workflow_id] = definition
            return definition

    async def add_step(
        self,
        workflow_id: str,
        parent_step_id: str,
        new_step: WorkflowStep,
    ) -> WorkflowDefinition:
        async with self._lock:
            definition = self._definitions.get(workflow_id)
            if definition is None:
                raise WorkflowNotFoundError(workflow_id)
            replaced_root = _add_child(definition.root, parent_step_id, new_step)
            definition = definition.model_copy(update={"root": replaced_root})
            self._definitions[workflow_id] = definition
            return definition

    async def remove_step(self, workflow_id: str, step_id: str) -> WorkflowDefinition:
        async with self._lock:
            definition = self._definitions.get(workflow_id)
            if definition is None:
                raise WorkflowNotFoundError(workflow_id)
            replaced_root = _remove_step(definition.root, step_id)
            definition = definition.model_copy(update={"root": replaced_root})
            self._definitions[workflow_id] = definition
            return definition


def _count_steps(step: WorkflowStep | None) -> int:
    if step is None:
        return 0
    return 1 + sum(_count_steps(child) for child in step.children)


def _patch_step(step: WorkflowStep, step_id: str, patch: WorkflowStepPatch) -> WorkflowStep:
    if step.id == step_id:
        data = step.model_dump()
        if patch.kind is not None:
            data["kind"] = patch.kind
        if patch.agent is not None:
            data["agent"] = patch.agent
        if patch.config is not None:
            data["config"] = patch.config
        return WorkflowStep(**data)
    updated_children = [
        _patch_step(child, step_id, patch)
        if _contains_step(child, step_id)
        else child
        for child in step.children
    ]
    return step.model_copy(update={"children": updated_children})


def _contains_step(step: WorkflowStep, step_id: str) -> bool:
    if step.id == step_id:
        return True
    return any(_contains_step(child, step_id) for child in step.children)


def _add_child(step: WorkflowStep, parent_id: str, new_step: WorkflowStep) -> WorkflowStep:
    if step.id == parent_id:
        return step.model_copy(update={"children": [*step.children, new_step]})
    updated_children = [
        _add_child(child, parent_id, new_step)
        if _contains_step(child, parent_id)
        else child
        for child in step.children
    ]
    return step.model_copy(update={"children": updated_children})


def _remove_step(step: WorkflowStep, step_id: str) -> WorkflowStep:
    filtered_children = [child for child in step.children if child.id != step_id]
    updated_children = [
        _remove_step(child, step_id) if _contains_step(child, step_id) else child
        for child in filtered_children
    ]
    return step.model_copy(update={"children": updated_children})


workflow_composer = WorkflowComposer()

__all__ = ["WorkflowComposer", "WorkflowComposerError", "WorkflowNotFoundError", "workflow_composer"]
