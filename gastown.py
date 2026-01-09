#!/usr/bin/env python3
"""
Google Gas Town - Multi-Agent Workspace Manager for Antigravity IDE

A port of Steve Yegge's Gas Town orchestration system, adapted for
Jules Agent CLI and Gemini ecosystem.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from lib.mayor import Mayor
from lib.rig import RigManager
from lib.convoy import ConvoyManager
from lib.dashboard import SwarmDashboard
from lib.config import load_config, save_config


async def cmd_install(args):
    """Initialize a Gas Town workspace."""
    workspace = Path(args.path).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    
    # Create workspace structure
    (workspace / "rigs").mkdir(exist_ok=True)
    (workspace / "hooks").mkdir(exist_ok=True)
    (workspace / "convoys").mkdir(exist_ok=True)
    (workspace / ".gastown").mkdir(exist_ok=True)
    
    # Initialize git if requested
    if args.git:
        os.system(f"git init {workspace}")
    
    config = {
        "workspace": str(workspace),
        "default_agent": "jules",
        "poll_interval": 5,
        "max_concurrent_agents": 4,
        "rate_limit_backoff": 30,
    }
    save_config(workspace / ".gastown" / "config.yaml", config)
    
    print(f"✓ Gas Town workspace initialized at {workspace}")
    print(f"  Run 'gt rig add <name> <repo>' to add your first project")


async def cmd_rig_add(args):
    """Add a project rig."""
    config = load_config()
    manager = RigManager(config["workspace"])
    await manager.add(args.name, args.repo)
    print(f"✓ Added rig '{args.name}' from {args.repo}")


async def cmd_rig_list(args):
    """List all rigs."""
    config = load_config()
    manager = RigManager(config["workspace"])
    rigs = await manager.list()
    
    if not rigs:
        print("No rigs configured. Use 'gt rig add <name> <repo>'")
        return
    
    print("Rigs:")
    for rig in rigs:
        print(f"  • {rig['name']}: {rig['repo']}")


async def cmd_spawn(args):
    """Spawn a Jules polecat worker for a task."""
    from lib.jules_wrapper import JulesWrapper
    from lib.polecat import Polecat
    
    config = load_config()
    wrapper = JulesWrapper(config)
    polecat = Polecat(wrapper, args.rig)
    
    job_id = await polecat.spawn(args.task, context_files=args.files or [])
    print(f"✓ Spawned polecat with job ID: {job_id}")
    print(f"  Monitor with 'gt status {job_id}'")


async def cmd_swarm(args):
    """Spawn N concurrent Jules workers."""
    from lib.jules_wrapper import JulesWrapper
    from lib.polecat import Polecat
    
    config = load_config()
    wrapper = JulesWrapper(config)
    
    # Parse tasks from convoy or args
    convoy_manager = ConvoyManager(config["workspace"])
    tasks = await convoy_manager.get_tasks(args.convoy)
    
    if not tasks:
        print("No tasks in convoy. Add tasks with 'gt convoy add-task'")
        return
    
    # Limit to requested count
    tasks = tasks[:args.count]
    
    dashboard = SwarmDashboard()
    polecats = []
    
    for task in tasks:
        polecat = Polecat(wrapper, task["rig"])
        polecats.append(polecat)
    
    # Launch all concurrently with dashboard updates
    await dashboard.run_swarm(polecats, tasks)


async def cmd_mayor_attach(args):
    """Start the Mayor coordinator session."""
    config = load_config()
    mayor = Mayor(config)
    
    print("🎩 Mayor session starting...")
    print("   Tell me what you want to accomplish.\n")
    
    await mayor.interactive_loop()


async def cmd_convoy_create(args):
    """Create a new convoy (task bundle)."""
    config = load_config()
    manager = ConvoyManager(config["workspace"])
    convoy_id = await manager.create(args.name, args.issues or [])
    print(f"✓ Created convoy '{args.name}' (ID: {convoy_id})")


async def cmd_convoy_status(args):
    """Show convoy status."""
    config = load_config()
    manager = ConvoyManager(config["workspace"])
    status = await manager.status(args.id)
    
    dashboard = SwarmDashboard()
    dashboard.render_convoy(status)


async def cmd_status(args):
    """Check status of a Jules job."""
    from lib.jules_wrapper import JulesWrapper
    
    config = load_config()
    wrapper = JulesWrapper(config)
    status = await wrapper.get_status(args.job_id)
    
    print(f"Job {args.job_id}:")
    print(f"  Status: {status.state}")
    print(f"  Step:   {status.current_step}")
    if status.pr_link:
        print(f"  PR:     {status.pr_link}")


async def cmd_checkout(args):
    """Checkout a PR locally for inspection."""
    from lib.hooks import HookManager
    
    config = load_config()
    hooks = HookManager(config["workspace"])
    local_path = await hooks.checkout_pr_locally(args.pr_id)
    print(f"✓ PR #{args.pr_id} checked out to: {local_path}")


async def cmd_glove(args):
    """Launch the White Glove interface."""
    from lib.glove import run_glove
    await run_glove(project=args.project)


def main():
    parser = argparse.ArgumentParser(
        prog="gt",
        description="Google Gas Town - Multi-Agent Workspace Manager"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # install
    p_install = subparsers.add_parser("install", help="Initialize workspace")
    p_install.add_argument("path", help="Workspace path (e.g., ~/gt)")
    p_install.add_argument("--git", action="store_true", help="Initialize git repo")
    p_install.set_defaults(func=cmd_install)
    
    # rig add
    p_rig = subparsers.add_parser("rig", help="Manage project rigs")
    rig_sub = p_rig.add_subparsers(dest="rig_cmd", required=True)
    
    p_rig_add = rig_sub.add_parser("add", help="Add a rig")
    p_rig_add.add_argument("name", help="Rig name")
    p_rig_add.add_argument("repo", help="Git repository URL")
    p_rig_add.set_defaults(func=cmd_rig_add)
    
    p_rig_list = rig_sub.add_parser("list", help="List rigs")
    p_rig_list.set_defaults(func=cmd_rig_list)
    
    # spawn
    p_spawn = subparsers.add_parser("spawn", help="Spawn a polecat worker")
    p_spawn.add_argument("task", help="Task description or issue ID")
    p_spawn.add_argument("--rig", required=True, help="Target rig")
    p_spawn.add_argument("--files", nargs="*", help="Context files")
    p_spawn.set_defaults(func=cmd_spawn)
    
    # swarm
    p_swarm = subparsers.add_parser("swarm", help="Spawn concurrent workers")
    p_swarm.add_argument("--convoy", required=True, help="Convoy ID")
    p_swarm.add_argument("--count", type=int, default=4, help="Number of workers")
    p_swarm.set_defaults(func=cmd_swarm)
    
    # mayor
    p_mayor = subparsers.add_parser("mayor", help="Mayor operations")
    mayor_sub = p_mayor.add_subparsers(dest="mayor_cmd", required=True)
    
    p_mayor_attach = mayor_sub.add_parser("attach", help="Start Mayor session")
    p_mayor_attach.set_defaults(func=cmd_mayor_attach)
    
    # convoy
    p_convoy = subparsers.add_parser("convoy", help="Manage convoys")
    convoy_sub = p_convoy.add_subparsers(dest="convoy_cmd", required=True)
    
    p_convoy_create = convoy_sub.add_parser("create", help="Create convoy")
    p_convoy_create.add_argument("name", help="Convoy name")
    p_convoy_create.add_argument("--issues", nargs="*", help="Issue IDs")
    p_convoy_create.set_defaults(func=cmd_convoy_create)
    
    p_convoy_status = convoy_sub.add_parser("status", help="Show status")
    p_convoy_status.add_argument("id", help="Convoy ID")
    p_convoy_status.set_defaults(func=cmd_convoy_status)
    
    # status
    p_status = subparsers.add_parser("status", help="Check job status")
    p_status.add_argument("job_id", help="Jules job ID")
    p_status.set_defaults(func=cmd_status)
    
    # checkout
    p_checkout = subparsers.add_parser("checkout", help="Checkout PR locally")
    p_checkout.add_argument("pr_id", help="Pull request ID")
    p_checkout.set_defaults(func=cmd_checkout)
    
    # glove (White Glove interface)
    p_glove = subparsers.add_parser(
        "glove", 
        aliases=["g"],
        help="Launch White Glove interface (user-friendly TUI)"
    )
    p_glove.add_argument("--project", "-p", help="Project to work on")
    p_glove.set_defaults(func=cmd_glove)
    
    args = parser.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
