from typing import Optional

EXECUTION_ID_KEY = "__execution_id"

# Fallback global for non-Temporal contexts. This is best-effort only and
# used when neither workflow nor activity runtime is available.
_EXECUTION_ID: Optional[str] = None


def set_execution_id(execution_id: Optional[str]) -> None:
    global _EXECUTION_ID
    _EXECUTION_ID = execution_id


def get_execution_id() -> Optional[str]:
    """Return the current Temporal run identifier to use for gateway routing.

    Priority:
    - If inside a Temporal workflow, return workflow.info().run_id
    - Else if inside a Temporal activity, return activity.info().workflow_run_id
    - Else fall back to the global (best-effort)
    """
    # Try workflow runtime first
    try:
        from temporalio import workflow  # type: ignore

        try:
            if workflow.in_workflow():
                return workflow.info().run_id
        except Exception:
            pass
    except Exception:
        pass

    # Then try activity runtime
    try:
        from temporalio import activity  # type: ignore

        try:
            info = activity.info()
            if info is not None and getattr(info, "workflow_run_id", None):
                return info.workflow_run_id
        except Exception:
            pass
    except Exception:
        pass

    # Fallback to module-global (primarily for non-Temporal contexts)
    return _EXECUTION_ID
