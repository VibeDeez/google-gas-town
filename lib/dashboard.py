"""
Swarm Dashboard - Rich-based UI for monitoring agent swarm.

Since Jules output isn't streaming text in the same way as Claude,
this dashboard provides a real-time view of all active agents.
"""

import asyncio
from typing import List, Optional, Callable, TYPE_CHECKING, Any
from datetime import datetime

try:
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.layout import Layout
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    # Define stubs for type checking
    if TYPE_CHECKING:
        from rich.table import Table


class SwarmDashboard:
    """
    Dashboard for monitoring a swarm of Jules agents.
    
    Uses the `rich` library for beautiful terminal UI with:
    - Live-updating table of agents
    - Status spinners
    - Progress tracking
    """
    
    def __init__(self):
        self.console = Console() if RICH_AVAILABLE else None
        self._agents: List[dict] = []
    
    async def run_swarm(self, polecats: List, tasks: List[dict]):
        """
        Run a swarm of polecats with live dashboard.
        
        Args:
            polecats: List of Polecat instances
            tasks: List of task dictionaries with 'description' key
        """
        if not RICH_AVAILABLE:
            await self._run_swarm_simple(polecats, tasks)
            return
        
        # Initialize agent tracking
        self._agents = [
            {
                "id": f"polecat-{i}",
                "task": task.get("description", "Unknown")[:40],
                "status": "⏳ Pending",
                "step": "Initializing",
                "job_id": None,
                "started": None,
                "polecat": polecat
            }
            for i, (polecat, task) in enumerate(zip(polecats, tasks))
        ]
        
        with Live(self._generate_table(), console=self.console, refresh_per_second=2) as live:
            # Spawn all concurrently
            spawn_tasks = []
            for i, (polecat, task) in enumerate(zip(polecats, tasks)):
                spawn_tasks.append(
                    self._spawn_and_track(i, polecat, task, live)
                )
            
            await asyncio.gather(*spawn_tasks)
        
        # Final summary
        self._print_summary()
    
    async def _spawn_and_track(self, index: int, polecat, task: dict, live):
        """Spawn a polecat and track its progress."""
        try:
            self._agents[index]["status"] = "🚀 Spawning"
            self._agents[index]["started"] = datetime.now()
            live.update(self._generate_table())
            
            # Spawn the polecat
            job_id = await polecat.spawn(
                task.get("description", ""),
                context_files=task.get("files", [])
            )
            
            self._agents[index]["job_id"] = job_id
            self._agents[index]["status"] = "🔄 Running"
            live.update(self._generate_table())
            
            # Watch with updates
            def update_status(msg: str):
                self._agents[index]["step"] = msg[-40:]
                live.update(self._generate_table())
            
            status = await polecat.wrapper.watch_job(job_id, callback_stdout=update_status)
            
            if status.state == "COMPLETED":
                self._agents[index]["status"] = "✅ Complete"
                self._agents[index]["step"] = status.pr_link or "Done"
            else:
                self._agents[index]["status"] = "❌ Failed"
                self._agents[index]["step"] = status.error or "Error"
            
            live.update(self._generate_table())
            
        except Exception as e:
            self._agents[index]["status"] = "❌ Error"
            self._agents[index]["step"] = str(e)[:40]
            live.update(self._generate_table())
    
    def _generate_table(self) -> "Table":
        """Generate the dashboard table."""
        table = Table(title="🐝 Swarm Dashboard", show_header=True, header_style="bold magenta")
        
        table.add_column("Agent", style="cyan", width=12)
        table.add_column("Task", style="white", width=35)
        table.add_column("Status", style="green", width=12)
        table.add_column("Current Step", style="yellow", width=35)
        table.add_column("Duration", style="dim", width=10)
        
        for agent in self._agents:
            duration = ""
            if agent["started"]:
                delta = datetime.now() - agent["started"]
                duration = f"{int(delta.total_seconds())}s"
            
            table.add_row(
                agent["id"],
                agent["task"],
                agent["status"],
                agent["step"],
                duration
            )
        
        return table
    
    def _print_summary(self):
        """Print final summary after swarm completes."""
        if not RICH_AVAILABLE:
            return
        
        completed = sum(1 for a in self._agents if "Complete" in a["status"])
        failed = sum(1 for a in self._agents if "Failed" in a["status"] or "Error" in a["status"])
        
        self.console.print()
        self.console.print(Panel(
            f"[bold green]✓ Completed: {completed}[/]  "
            f"[bold red]✗ Failed: {failed}[/]  "
            f"[bold]Total: {len(self._agents)}[/]",
            title="Swarm Complete"
        ))
    
    async def _run_swarm_simple(self, polecats: List, tasks: List[dict]):
        """Fallback swarm runner without rich library."""
        print(f"\n🐝 Starting swarm of {len(polecats)} workers...")
        print("-" * 60)
        
        async def spawn_one(i, polecat, task):
            desc = task.get("description", "Unknown")
            print(f"  [{i+1}] Spawning: {desc[:40]}...")
            try:
                job_id = await polecat.spawn(desc, context_files=task.get("files", []))
                print(f"  [{i+1}] Started: {job_id[:8]}...")
                
                status = await polecat.wrapper.watch_job(job_id)
                
                if status.state == "COMPLETED":
                    print(f"  [{i+1}] ✅ Complete: {status.pr_link or 'Done'}")
                else:
                    print(f"  [{i+1}] ❌ Failed: {status.error or 'Error'}")
            except Exception as e:
                print(f"  [{i+1}] ❌ Error: {e}")
        
        await asyncio.gather(*[
            spawn_one(i, p, t) 
            for i, (p, t) in enumerate(zip(polecats, tasks))
        ])
        
        print("-" * 60)
        print("✓ Swarm complete")
    
    def render_convoy(self, convoy_status: dict):
        """Render convoy status."""
        if not RICH_AVAILABLE:
            print(f"\nConvoy: {convoy_status.get('name', 'Unknown')}")
            print(f"Status: {convoy_status.get('status', 'Unknown')}")
            for task in convoy_status.get("tasks", []):
                print(f"  - {task.get('description', '')[:50]}")
            return
        
        table = Table(title=f"📦 Convoy: {convoy_status.get('name', 'Unknown')}")
        table.add_column("Task", style="white")
        table.add_column("Status", style="green")
        table.add_column("Assignee", style="cyan")
        
        for task in convoy_status.get("tasks", []):
            table.add_row(
                task.get("description", "")[:50],
                task.get("status", "pending"),
                task.get("assignee", "-")
            )
        
        self.console.print(table)
