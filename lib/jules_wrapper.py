"""
Jules CLI Wrapper - Async job handling for Jules Agent.

Handles the async/GitHub-based job pattern:
  submit_task() -> poll_status() -> get_result()
"""

import asyncio
import subprocess
import json
import uuid
from dataclasses import dataclass
from typing import Optional, List, Callable
from datetime import datetime


@dataclass
class JobStatus:
    """Status of a Jules job."""
    job_id: str
    state: str  # PENDING, RUNNING, COMPLETED, FAILED, RATE_LIMITED
    current_step: str
    pr_link: Optional[str] = None
    branch_name: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    
    def is_complete(self) -> bool:
        return self.state in ("COMPLETED", "FAILED")
    
    def is_running(self) -> bool:
        return self.state == "RUNNING"


class JulesWrapper:
    """
    Wrapper for Jules CLI with async job handling.
    
    Abstracts GitHub interaction so the Mayor sees a simple
    "Task -> Result" flow while handling the async complexity.
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.poll_interval = config.get("poll_interval", 5)
        self.backoff_time = config.get("rate_limit_backoff", 30)
        self._active_jobs: dict[str, JobStatus] = {}
    
    async def submit_task(
        self, 
        prompt: str, 
        repo: str,
        context_files: Optional[List[str]] = None
    ) -> str:
        """
        Submit a task to Jules.
        
        1. Creates a dedicated branch for this task
        2. Submits job to Jules targeting that branch
        3. Returns job ID for tracking
        """
        # Generate unique branch name
        branch_name = f"polecat-{uuid.uuid4().hex[:8]}"
        
        # Create branch (non-blocking via asyncio)
        await self._run_git(["checkout", "-b", branch_name], cwd=repo)
        
        # Build Jules command
        cmd = ["jules", "start"]
        
        # Add context files if provided
        if context_files:
            for f in context_files:
                cmd.extend(["--context", f])
        
        # Add the prompt
        cmd.extend(["--prompt", prompt])
        cmd.extend(["--branch", branch_name])
        
        # Submit to Jules (async)
        result = await self._run_jules(cmd)
        
        job_id = self._parse_job_id(result)
        
        # Track the job
        self._active_jobs[job_id] = JobStatus(
            job_id=job_id,
            state="PENDING",
            current_step="Initializing",
            branch_name=branch_name,
            started_at=datetime.now()
        )
        
        return job_id
    
    async def watch_job(
        self, 
        job_id: str, 
        callback_stdout: Optional[Callable[[str], None]] = None
    ) -> JobStatus:
        """
        Poll job status until completion with UI updates.
        
        Args:
            job_id: The Jules job ID to watch
            callback_stdout: Callback for status updates (e.g., to tmux pane)
        
        Returns:
            Final JobStatus with PR link if successful
        """
        consecutive_errors = 0
        max_errors = 3
        
        while True:
            try:
                status = await self.get_status(job_id)
                self._active_jobs[job_id] = status
                
                # Reset error counter on success
                consecutive_errors = 0
                
                # Update UI via callback
                if callback_stdout:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    msg = f"[{timestamp}] Job #{job_id[:8]}... Status: {status.state}"
                    if status.current_step:
                        msg += f" - {status.current_step}"
                    callback_stdout(msg)
                
                # Check for completion
                if status.is_complete():
                    status.completed_at = datetime.now()
                    return status
                
                # Check for rate limiting
                if status.state == "RATE_LIMITED":
                    if callback_stdout:
                        callback_stdout(f"⚠️  Rate limited. Backing off {self.backoff_time}s...")
                    await asyncio.sleep(self.backoff_time)
                    continue
                
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors >= max_errors:
                    return JobStatus(
                        job_id=job_id,
                        state="FAILED",
                        current_step="Polling failed",
                        error=str(e)
                    )
                await asyncio.sleep(self.poll_interval)
    
    async def get_status(self, job_id: str) -> JobStatus:
        """Get current status of a Jules job."""
        cmd = ["jules", "status", job_id, "--format", "json"]
        result = await self._run_jules(cmd)
        
        try:
            data = json.loads(result)
            return JobStatus(
                job_id=job_id,
                state=data.get("state", "UNKNOWN"),
                current_step=data.get("current_step", ""),
                pr_link=data.get("pr_url"),
                branch_name=data.get("branch")
            )
        except json.JSONDecodeError:
            # Fallback parsing for non-JSON output
            return self._parse_status_text(job_id, result)
    
    async def get_result(self, job_id: str) -> dict:
        """Get the result of a completed job."""
        status = await self.get_status(job_id)
        
        if not status.is_complete():
            raise ValueError(f"Job {job_id} is not complete")
        
        return {
            "job_id": job_id,
            "state": status.state,
            "pr_link": status.pr_link,
            "branch": status.branch_name,
            "duration": (
                (status.completed_at - status.started_at).total_seconds()
                if status.completed_at and status.started_at
                else None
            )
        }
    
    async def cancel(self, job_id: str) -> bool:
        """Cancel a running job."""
        cmd = ["jules", "cancel", job_id]
        try:
            await self._run_jules(cmd)
            if job_id in self._active_jobs:
                self._active_jobs[job_id].state = "CANCELLED"
            return True
        except Exception:
            return False
    
    def get_active_jobs(self) -> List[JobStatus]:
        """Get all active (non-complete) jobs."""
        return [
            j for j in self._active_jobs.values() 
            if not j.is_complete()
        ]
    
    # --- Private helpers ---
    
    async def _run_jules(self, cmd: List[str]) -> str:
        """Run a Jules CLI command asynchronously."""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            raise RuntimeError(f"Jules command failed: {stderr.decode()}")
        
        return stdout.decode()
    
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
    
    def _parse_job_id(self, output: str) -> str:
        """Parse job ID from Jules output."""
        # Try JSON first
        try:
            data = json.loads(output)
            return data.get("job_id", data.get("id", ""))
        except json.JSONDecodeError:
            pass
        
        # Fallback: look for patterns like "Job ID: xxx" or "Started job: xxx"
        import re
        patterns = [
            r"[Jj]ob\s*[Ii][Dd]:\s*(\S+)",
            r"[Ss]tarted\s+job:\s*(\S+)",
            r"^([a-f0-9-]{36})$"  # UUID pattern
        ]
        for pattern in patterns:
            match = re.search(pattern, output)
            if match:
                return match.group(1)
        
        # Last resort: use first line
        return output.strip().split()[0] if output.strip() else str(uuid.uuid4())
    
    def _parse_status_text(self, job_id: str, output: str) -> JobStatus:
        """Parse status from non-JSON text output."""
        output_lower = output.lower()
        
        if "complete" in output_lower or "success" in output_lower:
            state = "COMPLETED"
        elif "fail" in output_lower or "error" in output_lower:
            state = "FAILED"
        elif "running" in output_lower or "progress" in output_lower:
            state = "RUNNING"
        elif "rate" in output_lower and "limit" in output_lower:
            state = "RATE_LIMITED"
        else:
            state = "PENDING"
        
        return JobStatus(
            job_id=job_id,
            state=state,
            current_step=output.strip()[:100]
        )
