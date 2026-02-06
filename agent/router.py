"""Model router: selects the optimal model for each agent step based on budget."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agent.budget import BudgetTracker


class ModelTier(Enum):
    """Model capability tiers, from cheapest to most capable."""
    BUDGET = 1
    ECONOMY = 2
    STANDARD = 3
    PREMIUM = 4


class StepType(Enum):
    """What kind of work this agent step is doing."""
    PLAN = "plan"          # Analyzing task, creating plan
    EXECUTE = "execute"    # Writing code, making changes
    VERIFY = "verify"      # Checking work, running tests
    SIMPLE = "simple"      # Simple file reads, trivial operations


# How important model capability is for each step type (0-1)
STEP_CAPABILITY_WEIGHT = {
    StepType.PLAN: 0.6,
    StepType.EXECUTE: 1.0,
    StepType.VERIFY: 0.5,
    StepType.SIMPLE: 0.1,
}


@dataclass
class ModelInfo:
    """A model with its cost and capability metadata."""
    id: str
    provider: str
    tier: ModelTier
    input_cost_per_1m: float   # USD per 1M input tokens
    output_cost_per_1m: float  # USD per 1M output tokens
    context_window: int

    def estimate_call_cost(self, input_tokens: int = 2000, output_tokens: int = 1000) -> float:
        return (
            input_tokens * self.input_cost_per_1m / 1_000_000
            + output_tokens * self.output_cost_per_1m / 1_000_000
        )


# --- Model Registry ---
# Pricing as of early 2025. Update as needed.
MODEL_REGISTRY: list[ModelInfo] = [
    # Anthropic
    ModelInfo("claude-opus-4-20250514",      "anthropic", ModelTier.PREMIUM,  15.0,  75.0,  200_000),
    ModelInfo("claude-sonnet-4-20250514",    "anthropic", ModelTier.STANDARD,  3.0,  15.0,  200_000),
    ModelInfo("claude-haiku-3-5-20241022",   "anthropic", ModelTier.ECONOMY,   0.80,  4.0,  200_000),
    # OpenAI
    ModelInfo("o1",                          "openai",    ModelTier.PREMIUM,  15.0,  60.0,  200_000),
    ModelInfo("gpt-4o",                      "openai",    ModelTier.STANDARD,  2.50, 10.0,  128_000),
    ModelInfo("gpt-4o-mini",                 "openai",    ModelTier.ECONOMY,   0.15,  0.60, 128_000),
    # Google
    ModelInfo("gemini-2.0-pro",              "google",    ModelTier.STANDARD,  1.25, 10.0,  1_000_000),
    ModelInfo("gemini-2.0-flash",            "google",    ModelTier.ECONOMY,   0.10,  0.40, 1_000_000),
    ModelInfo("gemini-1.5-flash",            "google",    ModelTier.BUDGET,    0.075, 0.30, 1_000_000),
]


class ModelRouter:
    """Selects the best model for each step given the current budget state.

    Strategy:
    - For each step, calculate the per-step budget (remaining / estimated steps left)
    - Filter to models from available providers that fit within per-step budget
    - Among those, pick the highest-tier model (best capability)
    - Adjust based on step type: execution needs capability, simple tasks don't
    - If budget is critically low, always pick the cheapest available model
    """

    def __init__(self, available_providers: list[str], budget: BudgetTracker):
        self.budget = budget
        self.models = [m for m in MODEL_REGISTRY if m.provider in available_providers]
        if not self.models:
            raise ValueError("No models available for the detected providers")
        # Sort by cost (cheapest first) as a fallback ordering
        self.models.sort(key=lambda m: m.estimate_call_cost())

    def select(
        self,
        step_type: StepType = StepType.EXECUTE,
        estimated_input_tokens: int = 2000,
        estimated_output_tokens: int = 1000,
    ) -> ModelInfo:
        """Pick the best model for the current step."""
        per_step_budget = self.budget.budget_per_step
        capability_weight = STEP_CAPABILITY_WEIGHT[step_type]

        # If budget is critically low (<5% remaining), use cheapest model regardless
        if self.budget.utilization > 0.95:
            return self._cheapest()

        # Find all models that fit within per-step budget
        candidates: list[tuple[ModelInfo, float]] = []
        for model in self.models:
            cost = model.estimate_call_cost(estimated_input_tokens, estimated_output_tokens)
            if cost <= per_step_budget:
                candidates.append((model, cost))

        if not candidates:
            return self._cheapest()

        # Score each candidate: balance capability vs cost savings
        scored = []
        for model, cost in candidates:
            # Capability score: 0-1 based on tier
            cap_score = model.tier.value / ModelTier.PREMIUM.value
            # Savings score: how much budget this preserves for later steps
            savings_score = 1.0 - (cost / per_step_budget) if per_step_budget > 0 else 0
            # Combined: for execution steps, heavily weight capability
            # For simple steps, heavily weight savings
            score = (capability_weight * cap_score) + ((1 - capability_weight) * savings_score)
            scored.append((model, score, cost))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]

    def _cheapest(self) -> ModelInfo:
        return min(self.models, key=lambda m: m.estimate_call_cost())

    def get_model_by_id(self, model_id: str) -> ModelInfo | None:
        for m in self.models:
            if m.id == model_id:
                return m
        return None

    def cheapest_model(self) -> ModelInfo:
        return self._cheapest()

    def available_tiers(self) -> list[ModelTier]:
        return sorted(set(m.tier for m in self.models), key=lambda t: t.value)
