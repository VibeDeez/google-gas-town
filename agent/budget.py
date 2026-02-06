"""Budget tracking and cost-aware strategy engine."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CostRecord:
    """A single cost event."""
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    step: int


class BudgetTracker:
    """Tracks spend against a USD budget and advises on remaining capacity."""

    def __init__(self, total_budget: float):
        self.total_budget = total_budget
        self.spent = 0.0
        self.records: list[CostRecord] = []
        self._estimated_remaining_steps = 10  # default, refined after planning

    @property
    def remaining(self) -> float:
        return max(self.total_budget - self.spent, 0.0)

    @property
    def utilization(self) -> float:
        if self.total_budget == 0:
            return 1.0
        return self.spent / self.total_budget

    @property
    def estimated_remaining_steps(self) -> int:
        return max(self._estimated_remaining_steps, 1)

    @estimated_remaining_steps.setter
    def estimated_remaining_steps(self, value: int):
        self._estimated_remaining_steps = max(value, 1)

    @property
    def budget_per_step(self) -> float:
        return self.remaining / self.estimated_remaining_steps

    @property
    def avg_cost_per_step(self) -> float:
        if not self.records:
            return 0.0
        return self.spent / len(self.records)

    def record(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        input_cost_per_1m: float,
        output_cost_per_1m: float,
        step: int,
    ) -> float:
        """Record a completed LLM call. Returns cost of this call."""
        cost = (
            input_tokens * input_cost_per_1m / 1_000_000
            + output_tokens * output_cost_per_1m / 1_000_000
        )
        self.spent += cost
        self.records.append(CostRecord(model_id, input_tokens, output_tokens, cost, step))

        # Dynamically adjust remaining step estimate based on spend rate
        if len(self.records) >= 2 and self.avg_cost_per_step > 0:
            projected_steps_left = int(self.remaining / self.avg_cost_per_step)
            self._estimated_remaining_steps = max(projected_steps_left, 1)

        return cost

    def can_afford(self, estimated_cost: float) -> bool:
        return self.remaining >= estimated_cost

    def max_output_tokens(self, input_cost_per_1m: float, output_cost_per_1m: float,
                          estimated_input_tokens: int = 2000) -> int:
        """Max output tokens we can afford for one call, reserving budget for future steps."""
        budget_for_call = self.budget_per_step
        input_cost = estimated_input_tokens * input_cost_per_1m / 1_000_000
        budget_for_output = budget_for_call - input_cost
        if budget_for_output <= 0:
            return 256
        max_tokens = int(budget_for_output / (output_cost_per_1m / 1_000_000))
        return max(256, min(max_tokens, 16384))

    def summary(self) -> dict:
        return {
            "total_budget": self.total_budget,
            "spent": self.spent,
            "remaining": self.remaining,
            "utilization": self.utilization,
            "total_calls": len(self.records),
            "avg_cost_per_call": self.avg_cost_per_step,
            "records": self.records,
        }
