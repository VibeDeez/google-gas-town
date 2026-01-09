"""
Polecat - Ephemeral worker agent.

Polecats spawn, complete a task, and disappear.
They are the workhorses of the Gas Town swarm.
"""

import uuid
from typing import Optional, List
from dataclasses import dataclass
from datetime import datetime

from .jules_wrapper import JulesWrapper, JobStatus


@dataclass
class PolecatResult:
    """Result from a completed polecat task."""
    job_id: str
    status: str
    pr_link: Optional[str]
    branch: Optional[str]
    duration_seconds: Optional[float]
    error: Optional[str] = None


class Polecat:
    """
    Ephemeral worker agent that spawns, completes a task, and disappears.
    
    Each polecat:
    1. Gets assigned a specific task
    2. Creates its own branch for isolation
    3. Submits work to Jules
    4. Reports back when complete
    """
    
    def __init__(self, wrapper: JulesWrapper, rig: str):
        self.wrapper = wrapper
        self.rig = rig
        self.id = f"polecat-{uuid.uuid4().hex[:8]}"
        self.job_id: Optional[str] = None
        self.status: str = "idle"
        self.created_at = datetime.now()
    
    async def spawn(
        self, 
        task: str, 
        context_files: Optional[List[str]] = None,
        repo_path: Optional[str] = None
    ) -> str:
        """
        Spawn the polecat to work on a task.
        
        Args:
            task: Task description or prompt
            context_files: Optional list of files for context
            repo_path: Path to the repository
        
        Returns:
            Job ID for tracking
        """
        self.status = "spawning"
        
        # Use rig as repo path if not specified
        if repo_path is None:
            repo_path = self.rig
        
        # Submit to Jules
        self.job_id = await self.wrapper.submit_task(
            prompt=task,
            repo=repo_path,
            context_files=context_files
        )
        
        self.status = "running"
        return self.job_id
    
    async def wait_for_completion(self, callback=None) -> PolecatResult:
        """
        Wait for the polecat to complete its task.
        
        Args:
            callback: Optional callback for status updates
        
        Returns:
            PolecatResult with job outcome
        """
        if not self.job_id:
            return PolecatResult(
                job_id="",
                status="error",
                pr_link=None,
                branch=None,
                duration_seconds=None,
                error="Polecat never spawned"
            )
        
        status = await self.wrapper.watch_job(self.job_id, callback_stdout=callback)
        
        self.status = "complete" if status.state == "COMPLETED" else "failed"
        
        duration = None
        if status.completed_at and status.started_at:
            duration = (status.completed_at - status.started_at).total_seconds()
        
        return PolecatResult(
            job_id=self.job_id,
            status=status.state,
            pr_link=status.pr_link,
            branch=status.branch_name,
            duration_seconds=duration,
            error=status.error
        )
    
    async def cancel(self) -> bool:
        """Cancel the polecat's job."""
        if not self.job_id:
            return False
        
        success = await self.wrapper.cancel(self.job_id)
        if success:
            self.status = "cancelled"
        return success
    
    def is_running(self) -> bool:
        """Check if polecat is currently running."""
        return self.status == "running"
    
    def is_complete(self) -> bool:
        """Check if polecat has completed (success or failure)."""
        return self.status in ("complete", "failed", "cancelled")
