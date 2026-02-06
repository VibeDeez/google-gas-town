"""Core agent loop: budget-aware, model-agnostic coding agent."""

from __future__ import annotations

import os

from agent.budget import BudgetTracker
from agent.display import Display
from agent.providers import detect_providers
from agent.providers.base import Provider
from agent.router import ModelRouter, StepType
from agent.tools import ToolRegistry


MAX_STEPS = 200

SYSTEM_TEMPLATE = """\
You are a coding agent. Complete the user's task efficiently and correctly.

Working directory: {cwd}

## Budget
You have a strict budget. Every response you generate costs money.
- Total budget: ${total_budget:.4f}
- Spent so far: ${spent:.4f}
- Remaining: ${remaining:.4f}
- Estimated steps left: {est_steps}

## Efficiency guidelines
- Read files before editing to understand context
- Make precise, targeted edits — don't rewrite entire files unnecessarily
- Combine related reasoning in a single response
- Don't repeat yourself or explain obvious things
- Minimize unnecessary tool calls
- When the task is complete, call task_complete immediately

## Tools
You have access to file operations, shell commands, and search tools.
Use them to explore, modify, and verify code.
"""


class Agent:
    """Budget-aware coding agent that dynamically selects models to optimize cost."""

    def __init__(
        self,
        task: str,
        budget: float,
        working_dir: str = ".",
        providers: dict[str, Provider] | None = None,
    ):
        self.task = task
        self.working_dir = os.path.abspath(working_dir)
        self.budget_tracker = BudgetTracker(budget)
        self.display = Display(self.budget_tracker)
        self.tools = ToolRegistry(self.working_dir)
        self.messages: list[dict] = []
        self.completed = False

        # Detect or use provided providers
        self.providers = providers or detect_providers()
        if not self.providers:
            self.display.no_providers()
            raise SystemExit(1)

        self.router = ModelRouter(list(self.providers.keys()), self.budget_tracker)

        # Estimate initial step count based on task complexity
        self._estimate_steps()

    def _estimate_steps(self):
        """Rough heuristic for initial step count estimate."""
        words = len(self.task.split())
        if words < 30:
            self.budget_tracker.estimated_remaining_steps = 5
        elif words < 100:
            self.budget_tracker.estimated_remaining_steps = 10
        else:
            self.budget_tracker.estimated_remaining_steps = 20

    def _build_system_prompt(self) -> str:
        return SYSTEM_TEMPLATE.format(
            cwd=self.working_dir,
            total_budget=self.budget_tracker.total_budget,
            spent=self.budget_tracker.spent,
            remaining=self.budget_tracker.remaining,
            est_steps=self.budget_tracker.estimated_remaining_steps,
        )

    def _step_type_for(self, step: int) -> StepType:
        """Heuristic: first step is planning, last-ish steps are verification."""
        if step == 1:
            return StepType.PLAN
        # If we have tool results pending, we're mid-execution
        if self.messages and self.messages[-1].get("role") == "tool_result":
            return StepType.EXECUTE
        return StepType.EXECUTE

    def _estimate_context_tokens(self) -> int:
        """Rough estimate of current conversation token count."""
        total_chars = sum(
            len(str(m.get("content", ""))) for m in self.messages
        )
        return total_chars // 4  # ~4 chars per token

    def run(self) -> dict:
        """Execute the agent loop. Returns budget summary."""
        self.display.banner(self.task, self.budget_tracker.total_budget)
        self.display.providers_detected(list(self.providers.keys()))

        # Initial user message
        self.messages.append({"role": "user", "content": self.task})

        step = 0
        while not self.completed and step < MAX_STEPS:
            step += 1

            # Check budget
            cheapest = self.router.cheapest_model()
            min_cost = cheapest.estimate_call_cost(500, 100)
            if not self.budget_tracker.can_afford(min_cost):
                self.display.budget_exhausted()
                break

            # Select model
            step_type = self._step_type_for(step)
            context_tokens = self._estimate_context_tokens()
            model_info = self.router.select(
                step_type=step_type,
                estimated_input_tokens=context_tokens + 500,
                estimated_output_tokens=1000,
            )

            # Get the provider for this model
            provider = self.providers[model_info.provider]

            # Calculate max tokens we can afford
            max_tokens = self.budget_tracker.max_output_tokens(
                model_info.input_cost_per_1m,
                model_info.output_cost_per_1m,
                estimated_input_tokens=context_tokens + 500,
            )

            self.display.step_start(step, model_info.id, model_info.tier.name)

            # Make the LLM call
            try:
                result = provider.complete(
                    messages=self.messages,
                    tools=self.tools.definitions,
                    model=model_info.id,
                    system=self._build_system_prompt(),
                    max_tokens=max_tokens,
                )
            except Exception as e:
                self.display.error(f"Provider error: {e}")
                # Try falling back to cheapest model from a different provider
                fallback = self._try_fallback(model_info.provider, step)
                if fallback is None:
                    break
                result = fallback

            # Record cost
            cost = self.budget_tracker.record(
                model_id=model_info.id,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                input_cost_per_1m=model_info.input_cost_per_1m,
                output_cost_per_1m=model_info.output_cost_per_1m,
                step=step,
            )
            self.display.step_cost(cost)

            # Show assistant response
            if result.content:
                self.display.assistant_message(result.content)

            # Add assistant message to history
            self.messages.append({
                "role": "assistant",
                "content": result.content,
                "tool_calls": result.tool_calls if result.tool_calls else None,
            })

            # Process tool calls
            if result.tool_calls:
                for tc in result.tool_calls:
                    self.display.tool_call(tc.name, tc.arguments)

                    if tc.name == "task_complete":
                        self.completed = True
                        self.display.task_complete(tc.arguments.get("summary", ""))
                        break

                    tool_output = self.tools.execute(tc.name, tc.arguments)
                    self.display.tool_result(tc.name, tool_output)

                    self.messages.append({
                        "role": "tool_result",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": tool_output,
                    })
            elif not result.tool_calls and result.stop_reason == "end_turn":
                # Model finished without tool calls — it may be done
                # Give it one more chance to call task_complete
                if step > 1:
                    self.completed = True

            # Update remaining step estimate
            if not self.completed:
                self.budget_tracker.estimated_remaining_steps = max(
                    self.budget_tracker.estimated_remaining_steps - 1, 1
                )

        self.display.summary()
        return self.budget_tracker.summary()

    def _try_fallback(self, failed_provider: str, step: int):
        """Try a different provider if one fails."""
        for name, provider in self.providers.items():
            if name == failed_provider:
                continue
            try:
                cheapest = self.router.cheapest_model()
                return provider.complete(
                    messages=self.messages,
                    tools=self.tools.definitions,
                    model=cheapest.id,
                    system=self._build_system_prompt(),
                    max_tokens=1024,
                )
            except Exception:
                continue
        self.display.error("All providers failed.")
        return None
