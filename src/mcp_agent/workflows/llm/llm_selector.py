import json
from difflib import SequenceMatcher
from importlib import resources
from typing import Dict, List, Optional, TYPE_CHECKING
import os

from numpy import average
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from mcp.types import ModelHint, ModelPreferences
from mcp_agent.core.context_dependent import ContextDependent
from mcp_agent.tracing.telemetry import get_tracer

if TYPE_CHECKING:
    from mcp_agent.core.context import Context


class ModelBenchmarks(BaseModel):
    """
    Performance benchmarks for comparing different models.
    """

    __pydantic_extra__: dict[str, float] = Field(
        init=False
    )  # Enforces that extra fields are floats

    quality_score: float | None = None
    """A blended quality score for the model."""

    mmlu_score: float | None = None
    gsm8k_score: float | None = None
    bbh_score: float | None = None

    model_config = ConfigDict(extra="allow")


class ModelLatency(BaseModel):
    """
    Latency benchmarks for comparing different models.
    """

    time_to_first_token_ms: float = Field(gt=0)
    """ 
    Median Time to first token in milliseconds.
    """

    tokens_per_second: float = Field(gt=0)
    """
    Median output tokens per second.
    """


class ModelCost(BaseModel):
    """
    Cost benchmarks for comparing different models.
    """

    blended_cost_per_1m: float | None = None
    """
    Blended cost mixing input/output cost per 1M tokens.
    """

    input_cost_per_1m: float | None = None
    """
    Cost per 1M input tokens.
    """

    output_cost_per_1m: float | None = None
    """
    Cost per 1M output tokens.
    """


class ModelMetrics(BaseModel):
    """
    Model metrics for comparing different models.
    """

    cost: ModelCost
    speed: ModelLatency
    intelligence: ModelBenchmarks


class ModelInfo(BaseModel):
    """
    LLM metadata, including performance benchmarks.
    """

    name: str
    description: str | None = None
    provider: str
    context_window: int | None = None
    tool_calling: bool | None = None
    structured_outputs: bool | None = None
    metrics: ModelMetrics


class ModelSelector(ContextDependent):
    """
    A heuristic-based selector to choose the best model from a list of models.

    Because LLMs can vary along multiple dimensions, choosing the "best" model is
    rarely straightforward.  Different models excel in different areas—some are
    faster but less capable, others are more capable but more expensive, and so
    on.

    MCP's ModelPreferences interface allows servers to express their priorities across multiple
    dimensions to help clients make an appropriate selection for their use case.
    """

    def __init__(
        self,
        models: List[ModelInfo] = None,
        benchmark_weights: Dict[str, float] | None = None,
        context: Optional["Context"] = None,
    ):
        super().__init__(context=context)
        if not models:
            self.models = load_default_models()
        else:
            self.models = models

        if benchmark_weights:
            self.benchmark_weights = benchmark_weights
        else:
            # Defaults for how much to value each benchmark metric (must add to 1)
            self.benchmark_weights = {"mmlu": 0.4, "gsm8k": 0.3, "bbh": 0.3}

        if abs(sum(self.benchmark_weights.values()) - 1.0) > 1e-6:
            raise ValueError("Benchmark weights must sum to 1.0")

        self.max_values = self._calculate_max_scores(self.models)
        # Store provider keys in lowercase for simple, predictable lookup
        self.models_by_provider = self._models_by_provider(self.models)

    def select_best_model(
        self,
        model_preferences: ModelPreferences,
        provider: str | None = None,
        min_tokens: int | None = None,
        max_tokens: int | None = None,
        tool_calling: bool | None = None,
        structured_outputs: bool | None = None,
    ) -> ModelInfo:
        """
        Select the best model from a given list of models based on the given model preferences.

        Args:
            model_preferences: MCP ModelPreferences with cost, speed, and intelligence priorities
            provider: Optional provider to filter models by
            min_tokens: Minimum context window size (in tokens) required
            max_tokens: Maximum context window size (in tokens) allowed
            tool_calling: If True, only include models with tool calling support; if None, no filter
            structured_outputs: If True, only include models with structured outputs support; if None, no filter

        Returns:
            ModelInfo: The best model based on the preferences and filters

        Raises:
            ValueError: If no models match the specified criteria
        """
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.select_best_model"
        ) as span:
            if self.context.tracing_enabled and self.benchmark_weights:
                for k, v in self.benchmark_weights.items():
                    span.set_attribute(f"benchmark_weights.{k}", v)

            # Set tracing attributes for new parameters
            if min_tokens is not None:
                span.set_attribute("min_tokens", min_tokens)
            if max_tokens is not None:
                span.set_attribute("max_tokens", max_tokens)
            if tool_calling is not None:
                span.set_attribute("tool_calling", tool_calling)
            if structured_outputs is not None:
                span.set_attribute("structured_outputs", structured_outputs)

            models: List[ModelInfo] = []
            if provider:
                # Lowercase provider for normalized lookup
                provider_key = provider.lower()
                models = self.models_by_provider.get(provider_key, [])
                # Fallback: if we still have no models for this provider, don't fail; use all models
                if not models:
                    models = self.models
                span.set_attribute("provider", provider)
            else:
                models = self.models

            if not models:
                raise ValueError(
                    f"No models available for selection. Provider={provider}"
                )

            span.set_attribute("models", [model.name for model in models])

            candidate_models = models
            # First check the model hints
            if model_preferences.hints:
                candidate_models = []
                for model in models:
                    for hint in model_preferences.hints:
                        passes_hint = self._check_model_hint(model, hint)
                        span.set_attribute(f"model_hint.{hint.name}", passes_hint)
                        if passes_hint:
                            candidate_models.append(model)

                if not candidate_models:
                    # If no hints match, we'll use all models and let the benchmark weights decide
                    candidate_models = models

            # Filter by context window, tool calling, and structured outputs
            filtered_models = []
            for model in candidate_models:
                # Check context window constraints
                if min_tokens is not None and model.context_window is not None:
                    if model.context_window < min_tokens:
                        continue
                if max_tokens is not None and model.context_window is not None:
                    if model.context_window > max_tokens:
                        continue

                # Check tool calling requirement
                if tool_calling is not None and model.tool_calling is not None:
                    if tool_calling and not model.tool_calling:
                        continue

                # Check structured outputs requirement
                if (
                    structured_outputs is not None
                    and model.structured_outputs is not None
                ):
                    if structured_outputs and not model.structured_outputs:
                        continue

                filtered_models.append(model)

            candidate_models = filtered_models

            if not candidate_models:
                raise ValueError(
                    f"No models match the specified criteria. "
                    f"min_tokens={min_tokens}, max_tokens={max_tokens}, "
                    f"tool_calling={tool_calling}, structured_outputs={structured_outputs}"
                )

            scores = []

            # Next, we'll use the benchmark weights to decide the best model
            for model in candidate_models:
                cost_score = self._calculate_cost_score(
                    model, model_preferences, max_cost=self.max_values["max_cost"]
                )
                speed_score = self._calculate_speed_score(
                    model,
                    max_tokens_per_second=self.max_values["max_tokens_per_second"],
                    max_time_to_first_token_ms=self.max_values[
                        "max_time_to_first_token_ms"
                    ],
                )
                intelligence_score = self._calculate_intelligence_score(
                    model, self.max_values
                )

                model_score = (
                    (model_preferences.costPriority or 0) * cost_score
                    + (model_preferences.speedPriority or 0) * speed_score
                    + (model_preferences.intelligencePriority or 0) * intelligence_score
                )
                scores.append((model_score, model))

                if self.context.tracing_enabled:
                    span.set_attribute(f"model.{model.name}.cost_score", cost_score)
                    span.set_attribute(f"model.{model.name}.speed_score", speed_score)
                    span.set_attribute(
                        f"model.{model.name}.intelligence_score", intelligence_score
                    )
                    span.set_attribute(f"model.{model.name}.total_score", model_score)

            best_model = max(scores, key=lambda x: x[0])[1]
            span.set_attribute("best_model", best_model.name)
            return best_model

    def _models_by_provider(
        self, models: List[ModelInfo]
    ) -> Dict[str, List[ModelInfo]]:
        """
        Group models by provider.
        """
        provider_models: Dict[str, List[ModelInfo]] = {}
        for model in models:
            key = (model.provider or "").lower()
            if key not in provider_models:
                provider_models[key] = []
            provider_models[key].append(model)
        return provider_models

    def _check_model_hint(self, model: ModelInfo, hint: ModelHint) -> bool:
        """
        Check if a model matches a specific hint.
        """

        # Derive desired provider/name from hint. Support "provider:model" in hint.name
        desired_name: str | None = hint.name
        desired_provider: str | None = getattr(hint, "provider", None)
        if desired_name and ":" in desired_name and not desired_provider:
            lhs, rhs = desired_name.split(":", 1)
            if lhs.strip() and rhs.strip():
                desired_provider = lhs.strip()
                desired_name = rhs.strip()

        # Name match: exact (case-insensitive) then substring fallback
        name_match = True
        if desired_name:
            dn = desired_name.lower()
            mn = (model.name or "").lower()
            name_match = dn == mn or dn in mn or mn in dn

        # Provider match: exact (case-insensitive)
        provider_match = True
        if desired_provider:
            dp = desired_provider.lower()
            mp = (model.provider or "").lower()
            provider_match = dp == mp

        # Extend here for additional hint dimensions if needed
        return name_match and provider_match

    def _calculate_total_cost(self, model: ModelInfo, io_ratio: float = 3.0) -> float:
        """
        Calculate a single cost metric of a model based on input/output token costs,
        and a ratio of input to output tokens.

        Args:
            model: The model to calculate the cost for.
            io_ratio: The estimated ratio of input to output tokens. Defaults to 3.0.
        """

        if model.metrics.cost.blended_cost_per_1m is not None:
            return model.metrics.cost.blended_cost_per_1m

        input_cost = model.metrics.cost.input_cost_per_1m
        output_cost = model.metrics.cost.output_cost_per_1m

        # Handle missing values gracefully
        if input_cost is not None and output_cost is not None:
            return (input_cost * io_ratio + output_cost) / (1 + io_ratio)
        if input_cost is not None:
            return input_cost
        if output_cost is not None:
            return output_cost
        return 0.0

    def _calculate_cost_score(
        self,
        model: ModelInfo,
        model_preferences: ModelPreferences,
        max_cost: float,
    ) -> float:
        """Normalized 0->1 cost score for a model."""
        # Prefer the user-provided blend ratio if available; fallback to 3:1
        try:
            io_ratio = getattr(model_preferences, "ioRatio", 3.0) or 3.0
        except Exception:
            io_ratio = 3.0
        total_cost = self._calculate_total_cost(model, io_ratio)
        if max_cost <= 0:
            return 1.0
        return max(0.0, 1 - (total_cost / max_cost))

    def _calculate_intelligence_score(
        self, model: ModelInfo, max_values: Dict[str, float]
    ) -> float:
        """
        Return a normalized 0->1 intelligence score for a model based on its benchmark metrics.
        """
        scores = []
        weights = []

        benchmark_dict: Dict[str, float] = model.metrics.intelligence.model_dump()
        use_weights = True
        for bench, score in benchmark_dict.items():
            key = f"max_{bench}"
            if score is not None and key in max_values:
                scores.append(score / max_values[key])
                if bench in self.benchmark_weights:
                    weights.append(self.benchmark_weights[bench])
                else:
                    # If a benchmark doesn't have a weight, don't use weights at all, we'll just average the scores
                    use_weights = False

        if not scores:
            return 0
        elif use_weights:
            return average(scores, weights=weights)
        else:
            return average(scores)

    def _calculate_speed_score(
        self,
        model: ModelInfo,
        max_tokens_per_second: float,
        max_time_to_first_token_ms: float,
    ) -> float:
        """Normalized 0->1 cost score for a model."""

        time_to_first_token_score = 1 - (
            model.metrics.speed.time_to_first_token_ms / max_time_to_first_token_ms
        )

        tokens_per_second_score = (
            model.metrics.speed.tokens_per_second / max_tokens_per_second
        )

        latency_score = average(
            [time_to_first_token_score, tokens_per_second_score], weights=[0.4, 0.6]
        )
        return latency_score

    def _calculate_max_scores(self, models: List[ModelInfo]) -> Dict[str, float]:
        """
        Of all the models, calculate the maximum value for each benchmark metric.
        """
        max_dict: Dict[str, float] = {}

        max_dict["max_cost"] = max(self._calculate_total_cost(m) for m in models)
        max_dict["max_tokens_per_second"] = max(
            max(m.metrics.speed.tokens_per_second for m in models), 1e-6
        )
        max_dict["max_time_to_first_token_ms"] = max(
            max(m.metrics.speed.time_to_first_token_ms for m in models), 1e-6
        )

        # Find the maximum value for each model performance benchmark
        for model in models:
            benchmark_dict: Dict[str, float] = model.metrics.intelligence.model_dump()
            for bench, score in benchmark_dict.items():
                if score is None:
                    continue

                key = f"max_{bench}"
                if key in max_dict:
                    max_dict[key] = max(max_dict[key], score)
                else:
                    max_dict[key] = score

        return max_dict


_MODELS_CACHE: List[ModelInfo] | None = None


def load_default_models() -> List[ModelInfo]:
    """
    Load the embedded model catalog (ArtificialAnalysis benchmarks) once and cache it.
    Allows override via env var MCP_AGENT_MODELS_FILE pointing to a JSON file of ModelInfo records.
    """
    global _MODELS_CACHE
    if _MODELS_CACHE is not None:
        return _MODELS_CACHE

    override = os.environ.get("MCP_AGENT_MODELS_FILE")
    try:
        if override:
            with open(override, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            with (
                resources.files("mcp_agent.data")
                .joinpath("artificial_analysis_llm_benchmarks.json")
                .open()
            ) as file:
                data = json.load(file)
        adapter = TypeAdapter(List[ModelInfo])
        _MODELS_CACHE = adapter.validate_python(data)
    except Exception:
        _MODELS_CACHE = []
    return _MODELS_CACHE


def _fuzzy_match(str1: str, str2: str, threshold: float = 0.8) -> bool:
    """
    Fuzzy match two strings

    Args:
        str1: First string to compare
        str2: Second string to compare
        threshold: Minimum similarity ratio to consider a match (0.0 to 1.0)

    Returns:
        bool: True if strings match above threshold, False otherwise
    """
    sequence_ratio = SequenceMatcher(None, str1.lower(), str2.lower()).ratio()
    return sequence_ratio >= threshold
