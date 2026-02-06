"""CLI entry point for the budget-aware coding agent."""

from __future__ import annotations

import os
import sys

import click
from rich.console import Console

from agent.core import Agent

console = Console()


@click.group()
@click.version_option(package_name="budget-agent")
def main():
    """Budget-aware, model-agnostic coding agent.

    Give it a task and a dollar budget — it picks the best models
    and strategies to complete the task within cost.
    """


@main.command()
@click.argument("task")
@click.option("--budget", "-b", type=float, required=True, help="Budget in USD (e.g. 0.50)")
@click.option("--dir", "-d", "working_dir", default=".", help="Working directory (default: cwd)")
def run(task: str, budget: float, working_dir: str):
    """Run the agent on a task with a budget.

    \b
    Examples:
      agent run "Add input validation to app.py" --budget 0.25
      agent run "Refactor the auth module to use JWT" -b 1.00
      agent run "Write tests for utils.py" -b 0.10 -d ./myproject
    """
    if budget <= 0:
        console.print("[red]Budget must be positive.[/red]")
        sys.exit(1)

    agent = Agent(
        task=task,
        budget=budget,
        working_dir=os.path.abspath(working_dir),
    )
    agent.run()


@main.command()
def models():
    """List all known models and their pricing."""
    from rich.table import Table
    from agent.router import MODEL_REGISTRY

    table = Table(title="Available Models", border_style="cyan")
    table.add_column("Model ID", style="bold")
    table.add_column("Provider")
    table.add_column("Tier")
    table.add_column("Input $/1M", justify="right")
    table.add_column("Output $/1M", justify="right")
    table.add_column("Est. $/call", justify="right", style="green")
    table.add_column("Context", justify="right")

    for m in MODEL_REGISTRY:
        est = m.estimate_call_cost(2000, 1000)
        table.add_row(
            m.id, m.provider, m.tier.name,
            f"${m.input_cost_per_1m:.3f}", f"${m.output_cost_per_1m:.2f}",
            f"${est:.6f}", f"{m.context_window:,}",
        )

    console.print(table)

    # Show which providers are available
    from agent.providers import detect_providers
    providers = detect_providers()
    if providers:
        console.print(f"\n  [green]Active providers:[/green] {', '.join(providers.keys())}")
    else:
        console.print("\n  [yellow]No API keys detected. Set ANTHROPIC_API_KEY, "
                       "OPENAI_API_KEY, or GOOGLE_API_KEY.[/yellow]")


@main.command()
@click.argument("task")
@click.option("--budget", "-b", type=float, required=True, help="Budget in USD")
def estimate(task: str, budget: float):
    """Estimate what models/strategy the agent would use without running.

    \b
    Example:
      agent estimate "Add auth to Flask app" -b 0.50
    """
    from agent.budget import BudgetTracker
    from agent.providers import detect_providers
    from agent.router import ModelRouter, StepType
    from rich.table import Table

    providers = detect_providers()
    if not providers:
        console.print("[red]No providers available.[/red]")
        sys.exit(1)

    tracker = BudgetTracker(budget)
    words = len(task.split())
    if words < 30:
        tracker.estimated_remaining_steps = 5
    elif words < 100:
        tracker.estimated_remaining_steps = 10
    else:
        tracker.estimated_remaining_steps = 20

    router = ModelRouter(list(providers.keys()), tracker)

    console.print(f"\n  Task: [cyan]{task}[/cyan]")
    console.print(f"  Budget: [green]${budget:.4f}[/green]")
    console.print(f"  Estimated steps: {tracker.estimated_remaining_steps}")
    console.print(f"  Budget per step: ${tracker.budget_per_step:.6f}")
    console.print()

    table = Table(title="Model Selection by Step Type", border_style="cyan")
    table.add_column("Step Type")
    table.add_column("Selected Model", style="bold")
    table.add_column("Tier")
    table.add_column("Est. Cost/Call", justify="right")

    for st in StepType:
        model = router.select(step_type=st)
        cost = model.estimate_call_cost()
        table.add_row(st.value, model.id, model.tier.name, f"${cost:.6f}")

    console.print(table)

    cheapest = router.cheapest_model()
    max_calls = int(budget / cheapest.estimate_call_cost()) if cheapest.estimate_call_cost() > 0 else 999
    console.print(f"\n  Max possible calls (cheapest model): ~{max_calls}")
    console.print(f"  Cheapest model: {cheapest.id} @ ${cheapest.estimate_call_cost():.6f}/call")
