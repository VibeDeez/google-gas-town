"""
Mayor - The AI Coordinator for Gas Town.

The Mayor is the primary interface for orchestrating work across
multiple Jules agents. It uses an asyncio event loop to manage
concurrent workers without blocking.
"""

import asyncio
import sys
from typing import Optional, List
from datetime import datetime

from .jules_wrapper import JulesWrapper, JobStatus
from .brain import BrainManager


class Mayor:
    """
    The Mayor coordinates all Gas Town operations.
    
    Core responsibilities:
    - Break down user requests into discrete tasks
    - Create convoys for work tracking
    - Spawn and monitor polecat workers
    - Aggregate results and summarize progress
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.workspace = config.get("workspace", ".")
        self.max_concurrent = config.get("max_concurrent_agents", 4)
        
        self.wrapper = JulesWrapper(config)
        self.brain = BrainManager(config["workspace"])
        
        self._running = False
        self._active_jobs = {} # job_id -> task_text
    
    async def interactive_loop(self):
        """
        Main interactive loop for the Mayor session.
        
        This is the MEOW (Mayor-Enhanced Orchestration Workflow):
        1. User describes what they want
        2. Mayor analyzes and breaks down into tasks
        3. Creates convoy with issues
        4. Spawns appropriate agents
        5. Monitors progress
        6. Summarizes results
        """
        self._running = True
        
        print("=" * 60)
        print("  🎩 MAYOR SESSION - Google Gas Town")
        print("=" * 60)
        print()
        print("Commands:")
        print("  /spawn <task>     - Spawn a single worker")
        print("  /swarm <convoy>   - Launch convoy workers")
        print("  /status           - Show swarm dashboard")
        print("  /cancel <job_id>  - Cancel a job")
        print("  /quit             - Exit Mayor session")
        print()
        print("Or just describe what you want to accomplish.")
        print("-" * 60)
        
        while self._running:
            try:
                # 1. Check for completed jobs
                await self._check_jobs()
                
                # 2. Find next task
                await self._dispatch_next_task()
                
                # 3. Wait before next poll
                await asyncio.sleep(self.config.get("poll_interval", 5))
                
            except KeyboardInterrupt:

                self._running = False
                print("\n🎩 Mayor signing off.")
            except Exception as e:
                print(f"Error in Mayor loop: {e}")
                await asyncio.sleep(5)

    async def _dispatch_next_task(self):
        """Find pending tasks and spawn workers if capacity allows."""
        # Capacity check
        max_agents = self.config.get("max_concurrent_agents", 4)
        if len(self._active_jobs) >= max_agents:
            return

        # Get next pending task from Brain
        task_text = self.brain.get_next_pending_task()
        
        if task_text and task_text not in self._active_jobs.values():
            print(f"🎩 Spawning worker for: {task_text}")
            
            # Mark as running in file
            self.brain.mark_task_status(task_text, "running")
            
            # Spawn Jules
            try:
                rig_name = "default"
                # Check if rigs exist, find first one
                rigs_dir = self.brain.workspace / "rigs"
                if rigs_dir.exists():
                     for child in rigs_dir.iterdir():
                         if child.is_dir():
                             rig_name = child.name
                             break
                
                rig_path = str(self.brain.workspace / "rigs" / rig_name)
                job_id = await self.wrapper.submit_task(task_text, rig_path)
                
                self._active_jobs[job_id] = task_text
                
            except Exception as e:
                print(f"Failed to spawn for '{task_text}': {e}")
                self.brain.mark_task_status(task_text, "pending")

    async def _check_jobs(self):
        """Check status of all running jobs."""
        if not self._active_jobs:
            return

        # Copy keys to avoid modification during iteration
        for job_id in list(self._active_jobs.keys()):
            try:
                status = await self.wrapper.get_status(job_id)
                task_text = self._active_jobs[job_id]
                
                if status.state == "COMPLETED":
                    print(f"✅ Job {job_id} complete: {task_text}")
                    self.brain.mark_task_status(task_text, "done")
                    del self._active_jobs[job_id]
                    
                elif status.state in ("FAILED", "CANCELLED", "ERROR"):
                    print(f"❌ Job {job_id} failed: {task_text}")
                    self.brain.mark_task_status(task_text, "pending") 
                    del self._active_jobs[job_id]
            except Exception as e:
                print(f"Error checking job {job_id}: {e}")
