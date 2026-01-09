"""
Beads - Git-backed memory system for Gemini agents.

Adapted from Steve Yegge's Beads concept. In this port:
- A "Bead" is a pointer to a remote branch (not just local git state)
- When a Polecat finishes, the Bead captures the diff between main and jules-branch
- Context Maps provide structured repo navigation for Gemini's large context window
"""

import os
import asyncio
import json
import subprocess
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime
from dataclasses import dataclass, asdict


@dataclass
class Bead:
    """
    A Bead represents a unit of work state.
    
    Unlike local git snapshots, this Bead is a pointer to a remote branch,
    capturing the diff between main and the working branch.
    """
    id: str
    branch_name: str
    base_branch: str  # Usually 'main'
    created_at: str
    pr_id: Optional[str] = None
    pr_url: Optional[str] = None
    diff_summary: Optional[str] = None
    files_changed: Optional[List[str]] = None
    status: str = "active"  # active, merged, abandoned


class BeadsManager:
    """
    Manager for Beads - git-backed work state.
    
    Key differences from original Beads:
    1. Uses remote branches (not just local worktrees)
    2. Generates Context Maps for Gemini (structure over compression)
    3. Supports PR-based workflow integration
    """
    
    def __init__(self, workspace: str):
        self.workspace = Path(workspace)
        self.beads_dir = self.workspace / ".gastown" / "beads"
        self.beads_dir.mkdir(parents=True, exist_ok=True)
        self._beads: Dict[str, Bead] = {}
        self._load_beads()
    
    def _load_beads(self):
        """Load existing beads from disk."""
        beads_file = self.beads_dir / "beads.json"
        if beads_file.exists():
            try:
                data = json.loads(beads_file.read_text())
                for bead_data in data.get("beads", []):
                    bead = Bead(**bead_data)
                    self._beads[bead.id] = bead
            except (json.JSONDecodeError, TypeError):
                pass
    
    def _save_beads(self):
        """Persist beads to disk."""
        beads_file = self.beads_dir / "beads.json"
        data = {
            "beads": [asdict(b) for b in self._beads.values()],
            "updated_at": datetime.now().isoformat()
        }
        beads_file.write_text(json.dumps(data, indent=2))
    
    async def create_bead(
        self, 
        branch_name: str, 
        base_branch: str = "main",
        repo_path: Optional[str] = None
    ) -> Bead:
        """
        Create a new bead for a work branch.
        
        Args:
            branch_name: The feature/work branch name
            base_branch: The base branch (usually 'main')
            repo_path: Path to the git repository
        """
        import uuid
        
        bead_id = f"bead-{uuid.uuid4().hex[:8]}"
        
        bead = Bead(
            id=bead_id,
            branch_name=branch_name,
            base_branch=base_branch,
            created_at=datetime.now().isoformat()
        )
        
        # Get diff summary if repo path provided
        if repo_path:
            bead.diff_summary = await self._get_diff_summary(repo_path, base_branch, branch_name)
            bead.files_changed = await self._get_files_changed(repo_path, base_branch, branch_name)
        
        self._beads[bead_id] = bead
        self._save_beads()
        
        return bead
    
    async def capture_pr(self, bead_id: str, pr_id: str, pr_url: str):
        """Associate a PR with a bead."""
        if bead_id in self._beads:
            self._beads[bead_id].pr_id = pr_id
            self._beads[bead_id].pr_url = pr_url
            self._save_beads()
    
    async def get_context_map(self, repo_path: Optional[str] = None) -> Dict:
        """
        Generate a Context Map for Gemini.
        
        Instead of compressing context, we provide structured navigation:
        - File tree with descriptions
        - Key symbols (functions, classes) via ctags
        - Recent changes summary
        
        This leverages Gemini 3's large context window effectively.
        """
        if repo_path is None:
            repo_path = str(self.workspace)
        
        context = {
            "generated_at": datetime.now().isoformat(),
            "repo_path": repo_path,
            "files": [],
            "structure": {},
            "recent_changes": [],
            "key_symbols": []
        }
        
        # Get file tree
        context["structure"] = await self._get_file_tree(repo_path)
        
        # Get key files for context
        context["files"] = await self._get_key_files(repo_path)
        
        # Get recent changes
        context["recent_changes"] = await self._get_recent_changes(repo_path)
        
        # Get symbols if ctags available
        context["key_symbols"] = await self._get_symbols(repo_path)
        
        return context
    
    async def get_bead(self, bead_id: str) -> Optional[Bead]:
        """Get a bead by ID."""
        return self._beads.get(bead_id)
    
    async def list_beads(self, status: Optional[str] = None) -> List[Bead]:
        """List all beads, optionally filtered by status."""
        beads = list(self._beads.values())
        if status:
            beads = [b for b in beads if b.status == status]
        return sorted(beads, key=lambda b: b.created_at, reverse=True)
    
    async def update_bead_status(self, bead_id: str, status: str):
        """Update bead status (active, merged, abandoned)."""
        if bead_id in self._beads:
            self._beads[bead_id].status = status
            self._save_beads()
    
    # --- Private helpers ---
    
    async def _get_diff_summary(self, repo_path: str, base: str, branch: str) -> str:
        """Get a summary of changes between branches."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "diff", "--stat", f"{base}...{branch}",
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            return stdout.decode()[:1000]  # Limit size
        except Exception:
            return ""
    
    async def _get_files_changed(self, repo_path: str, base: str, branch: str) -> List[str]:
        """Get list of files changed between branches."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "diff", "--name-only", f"{base}...{branch}",
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            return stdout.decode().strip().split("\n")
        except Exception:
            return []
    
    async def _get_file_tree(self, repo_path: str, max_depth: int = 3) -> Dict:
        """Get file tree structure."""
        tree = {}
        
        try:
            for root, dirs, files in os.walk(repo_path):
                # Skip hidden and common ignore dirs
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'venv', '.venv']]
                
                rel_root = os.path.relpath(root, repo_path)
                depth = rel_root.count(os.sep)
                
                if depth > max_depth:
                    continue
                
                if rel_root == '.':
                    rel_root = ''
                
                current = tree
                if rel_root:
                    for part in rel_root.split(os.sep):
                        current = current.setdefault(part, {})
                
                for f in files[:20]:  # Limit files per dir
                    if not f.startswith('.'):
                        current[f] = "file"
        except Exception:
            pass
        
        return tree
    
    async def _get_key_files(self, repo_path: str) -> List[str]:
        """Get list of key files for context."""
        key_files = []
        key_patterns = [
            "README.md", "setup.py", "pyproject.toml", "package.json",
            "Makefile", "Dockerfile", "docker-compose.yml",
            "main.py", "app.py", "index.ts", "index.js"
        ]
        
        for root, _, files in os.walk(repo_path):
            for f in files:
                if f in key_patterns:
                    key_files.append(os.path.relpath(os.path.join(root, f), repo_path))
                    if len(key_files) >= 20:
                        return key_files
        
        return key_files
    
    async def _get_recent_changes(self, repo_path: str, limit: int = 10) -> List[Dict]:
        """Get recent git commits."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "log", f"-{limit}", "--pretty=format:%H|%s|%an|%ar",
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            
            changes = []
            for line in stdout.decode().strip().split("\n"):
                if "|" in line:
                    parts = line.split("|", 3)
                    if len(parts) >= 4:
                        changes.append({
                            "hash": parts[0][:8],
                            "message": parts[1],
                            "author": parts[2],
                            "when": parts[3]
                        })
            return changes
        except Exception:
            return []
    
    async def _get_symbols(self, repo_path: str) -> List[Dict]:
        """Get key symbols using ctags if available."""
        try:
            # Check if ctags is available
            proc = await asyncio.create_subprocess_exec(
                "ctags", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            
            if proc.returncode != 0:
                return []
            
            # Run ctags
            proc = await asyncio.create_subprocess_exec(
                "ctags", "-R", "--output-format=json", "--fields=+n",
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            
            symbols = []
            for line in stdout.decode().strip().split("\n")[:50]:
                try:
                    sym = json.loads(line)
                    symbols.append({
                        "name": sym.get("name"),
                        "kind": sym.get("kind"),
                        "file": sym.get("path")
                    })
                except json.JSONDecodeError:
                    continue
            
            return symbols
        except Exception:
            return []
