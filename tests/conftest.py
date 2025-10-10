import importlib
import sys
import types
from pathlib import Path


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
