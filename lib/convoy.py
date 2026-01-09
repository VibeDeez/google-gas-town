"""
Convoy - Work tracking and task bundles.

A Convoy bundles multiple issues/tasks that get assigned to agents.
"""

import json
import uuid
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime
from dataclasses import dataclass, asdict


@dataclass
class ConvoyTask:
    """A task within a convoy."""
    id: str
    description: str
    rig: str
    status: str  # pending, assigned, running, completed, failed
    assignee: Optional[str] = None  # polecat id
    job_id: Optional[str] = None
    pr_link: Optional[str] = None
    files: Optional[List[str]] = None


@dataclass
class Convoy:
    """A convoy is a bundle of related tasks."""
    id: str
    name: str
    created_at: str
    status: str  # pending, running, completed, partial
    tasks: List[ConvoyTask]


class ConvoyManager:
    """Manager for work tracking convoys."""
    
    def __init__(self, workspace: str):
        self.workspace = Path(workspace)
        self.convoys_dir = self.workspace / "convoys"
        self.convoys_dir.mkdir(parents=True, exist_ok=True)
        self._convoys: Dict[str, Convoy] = {}
        self._load_convoys()
    
    def _load_convoys(self):
        """Load existing convoys."""
        manifest = self.convoys_dir / "manifest.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text())
                for convoy_data in data.get("convoys", []):
                    # Reconstruct tasks
                    tasks = [ConvoyTask(**t) for t in convoy_data.get("tasks", [])]
                    convoy_data["tasks"] = tasks
                    convoy = Convoy(**convoy_data)
                    self._convoys[convoy.id] = convoy
            except (json.JSONDecodeError, TypeError):
                pass
    
    def _save_convoys(self):
        """Persist convoys."""
        manifest = self.convoys_dir / "manifest.json"
        data = {
            "convoys": [
                {
                    **{k: v for k, v in asdict(c).items() if k != "tasks"},
                    "tasks": [asdict(t) for t in c.tasks]
                }
                for c in self._convoys.values()
            ],
            "updated_at": datetime.now().isoformat()
        }
        manifest.write_text(json.dumps(data, indent=2))
    
    async def create(
        self, 
        name: str, 
        issues: List[str],
        rig: str = "default"
    ) -> str:
        """
        Create a new convoy.
        
        Args:
            name: Convoy name
            issues: List of task descriptions or issue IDs
            rig: Default rig for tasks
        
        Returns:
            Convoy ID
        """
        convoy_id = f"convoy-{uuid.uuid4().hex[:8]}"
        
        tasks = [
            ConvoyTask(
                id=f"task-{uuid.uuid4().hex[:8]}",
                description=issue,
                rig=rig,
                status="pending"
            )
            for issue in issues
        ]
        
        convoy = Convoy(
            id=convoy_id,
            name=name,
            created_at=datetime.now().isoformat(),
            status="pending",
            tasks=tasks
        )
        
        self._convoys[convoy_id] = convoy
        self._save_convoys()
        
        return convoy_id
    
    async def get(self, convoy_id: str) -> Optional[Convoy]:
        """Get a convoy by ID."""
        return self._convoys.get(convoy_id)
    
    async def get_tasks(self, convoy_id: str) -> List[Dict]:
        """Get tasks from a convoy."""
        convoy = self._convoys.get(convoy_id)
        if not convoy:
            return []
        
        return [asdict(t) for t in convoy.tasks]
    
    async def add_task(
        self, 
        convoy_id: str, 
        description: str,
        rig: str = "default",
        files: Optional[List[str]] = None
    ) -> Optional[str]:
        """Add a task to a convoy."""
        convoy = self._convoys.get(convoy_id)
        if not convoy:
            return None
        
        task = ConvoyTask(
            id=f"task-{uuid.uuid4().hex[:8]}",
            description=description,
            rig=rig,
            status="pending",
            files=files
        )
        
        convoy.tasks.append(task)
        self._save_convoys()
        
        return task.id
    
    async def assign_task(
        self, 
        convoy_id: str, 
        task_id: str,
        polecat_id: str,
        job_id: str
    ):
        """Assign a task to a polecat."""
        convoy = self._convoys.get(convoy_id)
        if not convoy:
            return
        
        for task in convoy.tasks:
            if task.id == task_id:
                task.assignee = polecat_id
                task.job_id = job_id
                task.status = "assigned"
                break
        
        self._update_convoy_status(convoy)
        self._save_convoys()
    
    async def update_task_status(
        self, 
        convoy_id: str, 
        task_id: str,
        status: str,
        pr_link: Optional[str] = None
    ):
        """Update a task's status."""
        convoy = self._convoys.get(convoy_id)
        if not convoy:
            return
        
        for task in convoy.tasks:
            if task.id == task_id:
                task.status = status
                if pr_link:
                    task.pr_link = pr_link
                break
        
        self._update_convoy_status(convoy)
        self._save_convoys()
    
    async def status(self, convoy_id: str) -> Dict:
        """Get convoy status summary."""
        convoy = self._convoys.get(convoy_id)
        if not convoy:
            return {"error": "Convoy not found"}
        
        task_summary = {
            "pending": 0,
            "assigned": 0,
            "running": 0,
            "completed": 0,
            "failed": 0
        }
        
        for task in convoy.tasks:
            if task.status in task_summary:
                task_summary[task.status] += 1
        
        return {
            "id": convoy.id,
            "name": convoy.name,
            "status": convoy.status,
            "created_at": convoy.created_at,
            "tasks": [asdict(t) for t in convoy.tasks],
            "summary": task_summary
        }
    
    async def list(self) -> List[Dict]:
        """List all convoys."""
        return [
            {
                "id": c.id,
                "name": c.name,
                "status": c.status,
                "task_count": len(c.tasks),
                "created_at": c.created_at
            }
            for c in self._convoys.values()
        ]
    
    def _update_convoy_status(self, convoy: Convoy):
        """Update convoy status based on task states."""
        if not convoy.tasks:
            convoy.status = "pending"
            return
        
        statuses = [t.status for t in convoy.tasks]
        
        if all(s == "completed" for s in statuses):
            convoy.status = "completed"
        elif all(s == "pending" for s in statuses):
            convoy.status = "pending"
        elif any(s == "running" or s == "assigned" for s in statuses):
            convoy.status = "running"
        elif any(s == "failed" for s in statuses):
            convoy.status = "partial"
        else:
            convoy.status = "running"
