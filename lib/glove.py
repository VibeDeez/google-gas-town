"""
White Glove Interface - User-friendly TUI for Gas Town.

Strips away technical friction (tmux, keyboard shortcuts) and provides
an idea-focused interface for spawning and managing Jules agent swarms.

Usage:
    gt glove           # Launch in current project
    gt g               # Short alias
    gt glove --project myproject
"""

import asyncio
import sys
from datetime import datetime
from typing import Optional, List, Dict, Callable
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    from rich.style import Style
    from rich.align import Align
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import InMemoryHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.formatted_text import HTML
    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False

from .config import load_config, find_workspace
from .mayor import Mayor
from .jules_wrapper import JulesWrapper
from .convoy import ConvoyManager
from .rig import RigManager


class WhiteGloveApp:
    """
    The White Glove interface - simple, idea-focused TUI.
    
    No tmux, no keyboard shortcuts, no terminal management.
    Just type what you want and watch it happen.
    """
    
    def __init__(self, project: Optional[str] = None):
        self.console = Console() if RICH_AVAILABLE else None
        self.config = load_config()
        self.workspace = find_workspace() or Path.home() / "gt"
        self.project = project
        
        # Components
        self.wrapper = JulesWrapper(self.config)
        from .brain import BrainManager
        self.brain = BrainManager(str(self.workspace))
        self._brain_tasks = []
        
        self.convoy_manager = ConvoyManager(str(self.workspace))
        self.rig_manager = RigManager(str(self.workspace))
        
        # State
        self._running = False
        self._active_jobs: List[Dict] = []
        self._recent_completions: List[Dict] = []
        self._command_history: List[str] = []
        
        # Input handling
        if PROMPT_TOOLKIT_AVAILABLE:
            self._history = InMemoryHistory()
            self._session = PromptSession(
                history=self._history,
                auto_suggest=AutoSuggestFromHistory()
            )
    
    async def run(self):
        """Main entry point for the White Glove interface."""
        if not RICH_AVAILABLE:
            print("White Glove requires 'rich' library. Install with: pip install rich")
            return
        
        self._running = True
        
        # Detect project if not specified
        if not self.project:
            self.project = await self._detect_project()
        
        # Welcome
        self._show_welcome()
        
        # Main loop
        await self._main_loop()
    
    async def _main_loop(self):
        """The main interaction loop."""
        while self._running:
            try:
                # Poll brain state
                # In a real app we'd use file watching or more efficient methods
                self._brain_tasks = self.brain.read_task_plan()
                
                # Render the interface
                self._render_interface()
                
                # Get user input
                user_input = await self._get_input()
                
                if not user_input:
                    continue
                
                # Handle input
                await self._handle_input(user_input)
                
            except KeyboardInterrupt:
                self._running = False
                self.console.print("\n[dim]Goodbye! 👋[/dim]")
            except EOFError:
                self._running = False
    
    def _show_welcome(self):
        """Show the welcome screen."""
        self.console.clear()
        
        welcome = Panel(
            Align.center(
                Text.from_markup(
                    "[bold cyan]🏗 GAS TOWN[/bold cyan]\n\n"
                    "[dim]White Glove Edition[/dim]\n\n"
                    "Type what you want to accomplish.\n"
                    "I'll handle the rest."
                ),
                vertical="middle"
            ),
            box=box.DOUBLE,
            style="cyan",
            height=12
        )
        self.console.print(welcome)
        self.console.print()
    
    def _render_interface(self):
        """Render the main interface."""
        self.console.print()
        
        # Header
        project_text = f"[bold cyan]{self.project or 'No Project'}[/bold cyan]"
        
        # Count stats from brain
        pending = sum(1 for t in self._brain_tasks if t['status'] == 'pending')
        running = sum(1 for t in self._brain_tasks if t['status'] == 'running')
        done = sum(1 for t in self._brain_tasks if t['status'] == 'done')
        
        status_text = f"[green]{running} active[/green] • [yellow]{pending} pending[/yellow] • [dim]{done} done[/dim]"
        
        header = Table.grid(expand=True)
        header.add_column(justify="left")
        header.add_column(justify="right")
        header.add_row(
            f"🏗 [bold]GAS TOWN[/bold]  ›  {project_text}",
            f"Tasks: {status_text}"
        )
        self.console.print(Panel(header, box=box.ROUNDED, style="cyan"))
        
        # Task Status (Brain)
        if self._brain_tasks:
            self._render_brain_status()
        
        # Help hint
        self.console.print(
            "[dim]  Enter: add task • Tab: suggest • Esc: menu • Ctrl+C: exit[/dim]"
        )
    
    def _render_brain_status(self):
        """Render the tasks from task.md."""
        table = Table(
            box=box.SIMPLE,
            show_header=True,
            header_style="bold",
            expand=True
        )
        table.add_column("State", width=3)
        table.add_column("Task", style="white")
        table.add_column("Status", width=12)
        
        # Limit to 10 most relevant (running first, then pending, then done)
        sorted_tasks = sorted(
            self._brain_tasks,
            key=lambda x: {"running": 0, "pending": 1, "done": 2}.get(x["status"], 3)
        )
        
        for task in sorted_tasks[:10]:
            icon = "⏳"
            style = "dim"
            status_text = "pending"
            
            if task["status"] == "running":
                icon = "🔄"
                style = "green"
                status_text = "running"
            elif task["status"] == "done":
                icon = "✅"
                style = "green"
                status_text = "done"
            
            table.add_row(
                icon,
                f"[{style}]{task['text'][:60]}[/{style}]",
                f"[{style}]{status_text}[/{style}]"
            )
        
        if len(sorted_tasks) > 10:
            table.add_row("", f"[dim]... and {len(sorted_tasks) - 10} more[/dim]", "")
        
        self.console.print(Panel(table, title="[bold]Brain Tasks[/bold]", border_style="blue"))
    
    async def _get_input(self) -> str:
        """Get user input with nice prompt."""
        try:
            if PROMPT_TOOLKIT_AVAILABLE:
                # Use prompt_toolkit for rich input
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._session.prompt(
                        HTML('<b>What would you like to do?</b>\n› '),
                        multiline=False
                    )
                )
                return result.strip()
            else:
                # Fallback to basic input
                self.console.print()
                result = input("What would you like to do?\n› ")
                return result.strip()
        except (KeyboardInterrupt, EOFError):
            raise
    
    async def _handle_input(self, text: str):
        """Process user input."""
        text = text.strip()
        
        if not text:
            return
        
        # Check for special commands
        if text.lower() in ("quit", "exit", "q"):
            self._running = False
            return
        
        if text.lower() in ("status", "s"):
            await self._show_detailed_status()
            return
        
        if text.lower() in ("help", "?", "h"):
            self._show_help()
            return
        
        if text.lower().startswith("project "):
            self.project = text[8:].strip()
            self.console.print(f"[green]✓ Switched to project: {self.project}[/green]")
            return
        
        # It's a task - process it
        await self._process_task(text)
    
    async def _process_task(self, task: str):
        """Process a natural language task request."""
        self.console.print()
        
        # Analyze the task
        tasks = self._break_down_task(task)
        
        self.console.print(f"[cyan]📋 Adding {len(tasks)} tasks to Brain...[/cyan]")
        
        # Instead of spawning immediately, we add to task.md
        # The Mayor loop running elsewhere (or in parallel) would pick it up
        # For this TUI app, we are just the interface.
        
        # Assuming we can append to task.md via BrainManager
        # Since create_new_task overwrites, we need an append method
        # or we manually append here using the manager's logic (which we don't have exposed yet)
        
        # For MVP, we'll re-read and append
        current_tasks = self.brain.read_task_plan()
        
        # We need a method to append tasks in BrainManager.
        # Since we can't change brain.py right now easily without another tool call,
        # let's assume valid access or just modify task.md directly if needed,
        # but better to stick to BrainManager abstraction if possible.
        # Wait, I didn't add an `append_task` method to brain.py in step 225.
        # I only added `create_new_task` (overwrite).
        # I should probably update brain.py first or implement a workaround.
        
        # Workaround: Read content, append lines, write back.
        # Accessing private props or just implementing here.
        
        content = self.brain.task_file.read_text(encoding="utf-8")
        if "## Execution Phase" not in content:
             content += "\n## Execution Phase\n"
        
        new_lines = ""
        for t in tasks:
            new_lines += f"- [ ] {t}\n"
            
        # Insert after Execution Phase header
        # Simple string replace
        parts = content.split("## Execution Phase")
        if len(parts) > 1:
            new_content = parts[0] + "## Execution Phase\n" + new_lines + parts[1]
        else:
            new_content = content + "\n\n## Execution Phase\n" + new_lines
            
        self.brain._write_file(self.brain.task_file, new_content)
        self.console.print(f"[green]✓ Added tasks to {self.brain.task_file}[/green]")

    
    def _break_down_task(self, task: str) -> List[str]:
        """Break down a task into subtasks."""
        # Simple heuristic: split on "and", "then", "also"
        separators = [" and ", " then ", " also ", "; ", ", then "]
        
        for sep in separators:
            if sep in task.lower():
                parts = task.split(sep)
                return [p.strip() for p in parts if p.strip()]
        
        return [task]
    
    async def _spawn_worker(self, task: str):
        """Spawn a single worker for a task."""
        job_info = {
            "task": task,
            "status": "spawning",
            "started": datetime.now(),
            "running": True,
            "job_id": None
        }
        self._active_jobs.append(job_info)
        
        try:
            # Submit to Jules
            job_id = await self.wrapper.submit_task(
                prompt=task,
                repo=str(self.workspace / "rigs" / (self.project or "default"))
            )
            
            job_info["job_id"] = job_id
            job_info["status"] = "running"
            
            self.console.print(f"[dim]  Started: {job_id[:12]}...[/dim]")
            
            # Watch in background
            asyncio.create_task(self._watch_worker(job_info))
            
        except Exception as e:
            job_info["status"] = "failed"
            job_info["running"] = False
            self.console.print(f"[red]  Error: {e}[/red]")
    
    async def _watch_worker(self, job_info: Dict):
        """Watch a worker until completion."""
        if not job_info.get("job_id"):
            return
        
        try:
            status = await self.wrapper.watch_job(job_info["job_id"])
            
            job_info["running"] = False
            job_info["status"] = status.state.lower()
            
            # Move to completions
            self._active_jobs.remove(job_info)
            self._recent_completions.insert(0, {
                "task": job_info["task"],
                "success": status.state == "COMPLETED",
                "pr_link": status.pr_link
            })
            
            # Keep only last 10
            self._recent_completions = self._recent_completions[:10]
            
            # Notify
            if status.state == "COMPLETED":
                pr_msg = f" → {status.pr_link}" if status.pr_link else ""
                self.console.print(f"\n[green]✅ Done:[/green] {job_info['task'][:30]}{pr_msg}")
            else:
                self.console.print(f"\n[red]❌ Failed:[/red] {job_info['task'][:30]}")
                
        except Exception as e:
            job_info["running"] = False
            job_info["status"] = "error"
    
    async def _show_detailed_status(self):
        """Show detailed status of all jobs."""
        self.console.clear()
        
        if not self._active_jobs:
            self.console.print("[dim]No active workers[/dim]")
            return
        
        table = Table(title="Active Workers", box=box.ROUNDED)
        table.add_column("Job ID", style="cyan")
        table.add_column("Task")
        table.add_column("Status", style="green")
        table.add_column("Elapsed")
        
        for job in self._active_jobs:
            table.add_row(
                (job.get("job_id") or "")[:12],
                job.get("task", "")[:40],
                job.get("status", "unknown"),
                self._format_elapsed(job.get("started"))
            )
        
        self.console.print(table)
        input("\nPress Enter to continue...")
    
    def _show_help(self):
        """Show help menu."""
        self.console.print(Panel(
            "[bold]Commands:[/bold]\n\n"
            "  [cyan]<your task>[/cyan]  - Describe what you want done\n"
            "  [cyan]status[/cyan]       - Show detailed worker status\n"
            "  [cyan]project X[/cyan]    - Switch to project X\n"
            "  [cyan]quit[/cyan]         - Exit White Glove\n\n"
            "[bold]Tips:[/bold]\n\n"
            "  • Just type naturally - 'Fix the login bug'\n"
            "  • Multiple tasks: 'Fix auth and add tests'\n"
            "  • I'll spawn workers automatically",
            title="[bold]Help[/bold]",
            border_style="cyan"
        ))
        input("\nPress Enter to continue...")
    
    async def _detect_project(self) -> Optional[str]:
        """Detect the current project from git or workspace."""
        cwd = Path.cwd()
        
        # Check if we're in a rig
        rigs_dir = self.workspace / "rigs"
        if rigs_dir in cwd.parents or cwd == rigs_dir:
            # Extract project name
            rel = cwd.relative_to(rigs_dir)
            return rel.parts[0] if rel.parts else None
        
        # Check for git remote
        try:
            import subprocess
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                cwd=cwd
            )
            if result.returncode == 0:
                url = result.stdout.strip()
                # Extract repo name
                name = url.split("/")[-1].replace(".git", "")
                return name
        except Exception:
            pass
        
        return None
    
    def _format_elapsed(self, started: Optional[datetime]) -> str:
        """Format elapsed time nicely."""
        if not started:
            return "-"
        
        delta = datetime.now() - started
        seconds = int(delta.total_seconds())
        
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m {seconds % 60}s"
        else:
            return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


async def run_glove(project: Optional[str] = None):
    """Entry point for the White Glove interface."""
    app = WhiteGloveApp(project=project)
    await app.run()
