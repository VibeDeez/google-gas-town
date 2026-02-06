"""Rich terminal display for budget-aware agent execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text
from rich.markdown import Markdown

if TYPE_CHECKING:
    from agent.budget import BudgetTracker

console = Console()


class Display:
    """Handles all terminal output with rich formatting."""

    def __init__(self, budget: BudgetTracker):
        self.budget = budget

    def banner(self, task: str, budget: float):
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bold cyan")
        table.add_column()
        table.add_row("Task:", task[:120])
        table.add_row("Budget:", f"${budget:.4f}")
        console.print(Panel(table, title="[bold]Budget Agent[/bold]", border_style="cyan"))

    def no_providers(self):
        console.print(
            Panel(
                "[bold red]No LLM providers detected.[/bold red]\n\n"
                "Set at least one API key:\n"
                "  ANTHROPIC_API_KEY\n"
                "  OPENAI_API_KEY\n"
                "  GOOGLE_API_KEY / GEMINI_API_KEY",
                title="Error",
                border_style="red",
            )
        )

    def providers_detected(self, providers: list[str]):
        console.print(f"  Providers: [green]{', '.join(providers)}[/green]")

    def step_start(self, step: int, model_id: str, tier: str):
        console.print()
        console.rule(f"[bold]Step {step}[/bold]")
        budget_bar = _budget_bar(self.budget)
        console.print(
            f"  Model: [yellow]{model_id}[/yellow] ({tier})  "
            f"Budget: {budget_bar} ${self.budget.remaining:.4f} remaining"
        )

    def step_cost(self, cost: float):
        color = "green" if cost < 0.01 else "yellow" if cost < 0.05 else "red"
        console.print(f"  Cost: [{color}]${cost:.6f}[/{color}]  "
                       f"Total: ${self.budget.spent:.4f} / ${self.budget.total_budget:.4f}")

    def assistant_message(self, content: str):
        if content.strip():
            console.print(Panel(Markdown(content), title="Agent", border_style="blue"))

    def tool_call(self, name: str, args: dict):
        args_str = ", ".join(f"{k}={_truncate(str(v), 60)}" for k, v in args.items())
        console.print(f"  [dim]-> {name}({args_str})[/dim]")

    def tool_result(self, name: str, result: str):
        truncated = _truncate(result, 200)
        console.print(f"  [dim]<- {name}: {truncated}[/dim]")

    def task_complete(self, summary: str):
        console.print()
        console.print(Panel(summary or "Task completed.", title="[bold green]Done[/bold green]",
                            border_style="green"))

    def budget_exhausted(self):
        console.print()
        console.print(Panel(
            f"[bold yellow]Budget exhausted.[/bold yellow]\n"
            f"Spent ${self.budget.spent:.4f} of ${self.budget.total_budget:.4f}",
            title="Budget Limit",
            border_style="yellow",
        ))

    def error(self, msg: str):
        console.print(f"  [bold red]Error:[/bold red] {msg}")

    def summary(self):
        info = self.budget.summary()
        console.print()
        table = Table(title="Execution Summary", border_style="cyan")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")
        table.add_row("Total Budget", f"${info['total_budget']:.4f}")
        table.add_row("Total Spent", f"${info['spent']:.6f}")
        table.add_row("Remaining", f"${info['remaining']:.4f}")
        table.add_row("Utilization", f"{info['utilization']:.1%}")
        table.add_row("LLM Calls", str(info['total_calls']))
        table.add_row("Avg Cost/Call", f"${info['avg_cost_per_call']:.6f}")
        console.print(table)

        if info["records"]:
            breakdown = Table(title="Cost Breakdown", border_style="dim")
            breakdown.add_column("#", style="dim")
            breakdown.add_column("Model")
            breakdown.add_column("In Tokens", justify="right")
            breakdown.add_column("Out Tokens", justify="right")
            breakdown.add_column("Cost", justify="right")
            for r in info["records"]:
                breakdown.add_row(
                    str(r.step), r.model,
                    f"{r.input_tokens:,}", f"{r.output_tokens:,}",
                    f"${r.cost:.6f}",
                )
            console.print(breakdown)


def _budget_bar(budget: BudgetTracker) -> str:
    pct = 1.0 - budget.utilization
    filled = int(pct * 20)
    empty = 20 - filled
    color = "green" if pct > 0.5 else "yellow" if pct > 0.2 else "red"
    return f"[{color}]{'█' * filled}{'░' * empty}[/{color}]"


def _truncate(s: str, max_len: int) -> str:
    s = s.replace("\n", "\\n")
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s
