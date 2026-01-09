"""
Rig - Project container management.

A Rig wraps a git repository and manages its associated agents.
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime
from dataclasses import dataclass, asdict


@dataclass
class Rig:
    """A rig represents a project container."""
    name: str
    repo: str
    local_path: str
    created_at: str
    default_branch: str = "main"
    active_agents: int = 0


class RigManager:
    """Manager for project rigs."""
    
    def __init__(self, workspace: str):
        self.workspace = Path(workspace)
        self.rigs_dir = self.workspace / "rigs"
        self.rigs_dir.mkdir(parents=True, exist_ok=True)
        self._rigs: Dict[str, Rig] = {}
        self._load_rigs()
    
    def _load_rigs(self):
        """Load existing rigs from manifest."""
        manifest = self.rigs_dir / "manifest.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text())
                for rig_data in data.get("rigs", []):
                    rig = Rig(**rig_data)
                    self._rigs[rig.name] = rig
            except (json.JSONDecodeError, TypeError):
                pass
    
    def _save_rigs(self):
        """Persist rigs manifest."""
        manifest = self.rigs_dir / "manifest.json"
        data = {
            "rigs": [asdict(r) for r in self._rigs.values()],
            "updated_at": datetime.now().isoformat()
        }
        manifest.write_text(json.dumps(data, indent=2))
    
    async def add(self, name: str, repo: str) -> Rig:
        """
        Add a new project rig.
        
        Args:
            name: Rig name (identifier)
            repo: Git repository URL
        
        Returns:
            The created Rig
        """
        local_path = str(self.rigs_dir / name)
        
        # Clone the repository
        await self._run_git(["clone", repo, local_path])
        
        # Get default branch
        default_branch = await self._get_default_branch(local_path)
        
        rig = Rig(
            name=name,
            repo=repo,
            local_path=local_path,
            created_at=datetime.now().isoformat(),
            default_branch=default_branch
        )
        
        self._rigs[name] = rig
        self._save_rigs()
        
        return rig
    
    async def get(self, name: str) -> Optional[Rig]:
        """Get a rig by name."""
        return self._rigs.get(name)
    
    async def list(self) -> List[Dict]:
        """List all rigs."""
        return [asdict(r) for r in self._rigs.values()]
    
    async def remove(self, name: str) -> bool:
        """Remove a rig."""
        if name not in self._rigs:
            return False
        
        rig = self._rigs[name]
        
        # Remove local directory
        import shutil
        if os.path.exists(rig.local_path):
            shutil.rmtree(rig.local_path)
        
        del self._rigs[name]
        self._save_rigs()
        
        return True
    
    async def update(self, name: str) -> bool:
        """Update a rig (git pull)."""
        rig = self._rigs.get(name)
        if not rig:
            return False
        
        await self._run_git(["pull"], cwd=rig.local_path)
        return True
    
    async def _run_git(self, args: List[str], cwd: Optional[str] = None) -> str:
        """Run a git command."""
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
    
    async def _get_default_branch(self, repo_path: str) -> str:
        """Get the default branch of a repository."""
        try:
            result = await self._run_git(
                ["symbolic-ref", "refs/remotes/origin/HEAD", "--short"],
                cwd=repo_path
            )
            # Returns something like "origin/main"
            return result.strip().split("/")[-1]
        except Exception:
            return "main"
