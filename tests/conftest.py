import asyncio
import importlib
import inspect
import sys
import types
from pathlib import Path

import pytest


_ASYNCIO_MARK_ATTR = "_mcp_asyncio_marker"


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if SRC.exists():
    sys.path.insert(0, str(SRC))


collect_ignore_glob: list[str] = []
collect_ignore: list[str] = []


def _ignore_paths(patterns: list[str]) -> None:
    collect_ignore_glob.extend(patterns)
    tests_dir = ROOT / "tests"
    if tests_dir.exists():
        for pattern in patterns:
            for path in tests_dir.glob(pattern):
                if path.is_file():
                    collect_ignore.append(str(path.relative_to(tests_dir)))


_ignore_paths(["bootstrap/test_plan_and_guard.py"])


def _ignore_if_missing(module_name: str, patterns: list[str]) -> None:
    try:
        importlib.import_module(module_name)
    except Exception:  # pragma: no cover - best effort skipping of optional deps
        _ignore_paths(patterns)


_OPTIONAL_DEPENDENCY_TESTS: dict[str, list[str]] = {
    "azure.ai.inference.models": [
        "utils/test_multipart_converter_azure.py",
        "workflows/llm/test_augmented_llm_azure.py",
    ],
    "boto3": ["workflows/llm/test_augmented_llm_bedrock.py"],
    "cohere": [
        "workflows/intent_classifier/test_intent_classifier_embedding_cohere.py",
        "workflows/router/test_router_embedding_cohere.py",
    ],
    "crewai.tools": ["tools/test_crewai_tool.py"],
    "google.genai": [
        "utils/test_multipart_converter_google.py",
        "workflows/llm/test_augmented_llm_google.py",
    ],
    "langchain_core.tools": ["tools/test_langchain_tool.py"],
    "pytest_asyncio": [
        "cli/**/*.py",
        "executor/**/*.py",
        "sentinel/test_authorize_matrix.py",
        "sentinel/test_deny_integration.py",
        "tracing/**/*.py",
        "workflows/**/*.py",
    ],
    "temporalio": [
        "executor/temporal/*.py",
        "human_input/*.py",
        "workflows/**/*.py",
    ],
}

for module_name, patterns in _OPTIONAL_DEPENDENCY_TESTS.items():
    _ignore_if_missing(module_name, patterns)

if "jwt" not in sys.modules:  # pragma: no cover - testing shim
    jwt_module = types.ModuleType("jwt")
    jwt_module.encode = lambda *args, **kwargs: ""
    jwt_module.decode = lambda *args, **kwargs: {}
    sys.modules["jwt"] = jwt_module


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "asyncio: run the marked test using an asyncio event loop",
    )


def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    del session  # unused but kept for hook signature compatibility
    has_anyio = config.pluginmanager.hasplugin("anyio")
    for item in items:
        if item.get_closest_marker("asyncio"):
            setattr(item, _ASYNCIO_MARK_ATTR, True)
            if has_anyio:
                item.add_marker(pytest.mark.anyio)


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> object:
    if not getattr(pyfuncitem, _ASYNCIO_MARK_ATTR, False):
        return None
    test_func = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_func):
        return None
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        coroutine = test_func(**pyfuncitem.funcargs)
        loop.run_until_complete(coroutine)
        loop.run_until_complete(loop.shutdown_asyncgens())
    finally:
        asyncio.set_event_loop(None)
        loop.close()
    return True
