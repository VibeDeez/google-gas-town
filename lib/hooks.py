"""
Hooks - Git worktree persistence layer.

Hooks provide persistent storage for agent work using git worktrees.
They survive crashes and restarts.
"""

import asyncio
import os
import json
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime
from dataclasses import dataclass, asdict


@dataclass
class Hook:
    """A hook represents a persistent worktree for agent work."""
    id: str
    rig: str
    branch_name: str
    worktree_path: str
    state: str  # created, active, suspended, completed, archived
    created_at: str
    job_id: Optional[str] = None
    pr_id: Optional[str] = None


class HookManager:
    """
    Manager for git worktree-based hooks.
    
    Hooks provide:
    1. Persistent state - Work survives agent restarts
    2. Version control - All changes tracked in git
    3. Rollback capability - Revert to any previous state
    4. Multi-agent coordination - Shared through git
    """
    
    def __init__(self, workspace: str):
        self.workspace = Path(workspace)
        self.hooks_dir = self.workspace / "hooks"
        self.hooks_dir.mkdir(parents=True, exist_ok=True)
        self._hooks: Dict[str, Hook] = {}
        self._load_hooks()
    
    def _load_hooks(self):
        """Load existing hooks from manifest."""
        manifest = self.hooks_dir / "manifest.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text())
                for hook_data in data.get("hooks", []):
                    hook = Hook(**hook_data)
                    self._hooks[hook.id] = hook
            except (json.JSONDecodeError, TypeError):
                pass
    
    def _save_hooks(self):
        """Persist hooks manifest."""
        manifest = self.hooks_dir / "manifest.json"
        data = {
            "hooks": [asdict(h) for h in self._hooks.values()],
            "updated_at": datetime.now().isoformat()
        }
        manifest.write_text(json.dumps(data, indent=2))
    
    async def create_hook(self, rig: str, branch_name: str, repo_path: str) -> Hook:
        """
        Create a new hook (git worktree) for agent work.
        
        Args:
            rig: The rig this hook belongs to
            branch_name: The branch to create worktree for
            repo_path: Path to the git repository
        """
        import uuid
        
        hook_id = f"hook-{uuid.uuid4().hex[:8]}"
        worktree_path = str(self.hooks_dir / hook_id)
        
        # Create git worktree
        await self._run_git(
            ["worktree", "add", worktree_path, "-b", branch_name],
            cwd=repo_path
        )
        
        hook = Hook(
            id=hook_id,
            rig=rig,
            branch_name=branch_name,
            worktree_path=worktree_path,
            state="created",
            created_at=datetime.now().isoformat()
        )
        
        self._hooks[hook_id] = hook
        self._save_hooks()
        
        return hook
    
    async def get_hook(self, hook_id: str) -> Optional[Hook]:
        """Get a hook by ID."""
        return self._hooks.get(hook_id)
    
    async def list_hooks(self, rig: Optional[str] = None, state: Optional[str] = None) -> List[Hook]:
        """List hooks, optionally filtered."""
        hooks = list(self._hooks.values())
        if rig:
            hooks = [h for h in hooks if h.rig == rig]
        if state:
            hooks = [h for h in hooks if h.state == state]
        return hooks
    
    async def update_state(self, hook_id: str, state: str):
        """Update hook state."""
        if hook_id in self._hooks:
            self._hooks[hook_id].state = state
            self._save_hooks()
    
    async def associate_job(self, hook_id: str, job_id: str):
        """Associate a Jules job with a hook."""
        if hook_id in self._hooks:
            self._hooks[hook_id].job_id = job_id
            self._hooks[hook_id].state = "active"
            self._save_hooks()
    
    async def checkout_pr_locally(self, pr_id: str, repo_path: Optional[str] = None) -> str:
        """
        Checkout a PR locally for inspection.
        
        This allows the user to instantly inspect Jules' work in their IDE.
        
        Args:
            pr_id: The pull request ID or number
            repo_path: Path to the repository
        
        Returns:
            Local path where the PR is checked out
        """
        if repo_path is None:
            # Try to find from existing hooks
            for hook in self._hooks.values():
                if hook.pr_id == pr_id:
                    return hook.worktree_path
            repo_path = str(self.workspace / "rigs" / "default")
        
        # Fetch the PR ref
        await self._run_git(
            ["fetch", "origin", f"pull/{pr_id}/head:pr-{pr_id}"],
            cwd=repo_path
        )
        
        # Create worktree for the PR
        hook_id = f"pr-{pr_id}"
        worktree_path = str(self.hooks_dir / hook_id)
        
        if not os.path.exists(worktree_path):
            await self._run_git(
                ["worktree", "add", worktree_path, f"pr-{pr_id}"],
                cwd=repo_path
            )
        
        # Track in hooks
        if hook_id not in self._hooks:
            self._hooks[hook_id] = Hook(
                id=hook_id,
                rig="pr-review",
                branch_name=f"pr-{pr_id}",
                worktree_path=worktree_path,
                state="active",
                created_at=datetime.now().isoformat(),
                pr_id=pr_id
            )
            self._save_hooks()
        
        return worktree_path
    
    async def archive_hook(self, hook_id: str, repo_path: str):
        """Archive a completed hook by removing worktree."""
        hook = self._hooks.get(hook_id)
        if not hook:
            return
        
        # Remove worktree
        try:
            await self._run_git(
                ["worktree", "remove", hook.worktree_path, "--force"],
                cwd=repo_path
            )
        except Exception:
            pass
        
        hook.state = "archived"
        self._save_hooks()
    
    async def get_worktree_status(self, hook_id: str) -> Dict:
        """Get git status of a hook's worktree."""
        hook = self._hooks.get(hook_id)
        if not hook or not os.path.exists(hook.worktree_path):
            return {"error": "Hook not found"}
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "status", "--porcelain",
                cwd=hook.worktree_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            
            changes = []
            for line in stdout.decode().strip().split("\n"):
                if line:
                    status = line[:2].strip()
                    filename = line[3:]
                    changes.append({"status": status, "file": filename})
            
            return {
                "hook_id": hook_id,
                "branch": hook.branch_name,
                "changes": changes,
                "clean": len(changes) == 0
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def _run_git(self, args: List[str], cwd: str) -> str:
        """Run a git command asynchronously."""
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            raise RuntimeError(f"Git command failed: {stderr.decode()}")
        
        return stdout.decode()
