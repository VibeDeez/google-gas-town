"""
Brain Manager - Handles Antigravity Agent Tasks artifacts (task.md, etc).

The Brain is the persistent memory of the Mayor, stored in markdown files
that are compatible with Antigravity IDE's Agentic Mode.
"""

import os
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple

class BrainManager:
    """Read and write task.md and implementation_plan.md."""

    def __init__(self, workspace_path: str):
        self.workspace = Path(workspace_path)
        # Store brain in .gastown/brain unless overriden
        self.brain_dir = self.workspace / ".gastown" / "brain"
        self.task_file = self.brain_dir / "task.md"
        self.plan_file = self.brain_dir / "implementation_plan.md"
        
        self._ensure_brain_exists()

    def _ensure_brain_exists(self):
        """Ensure the brain directory and initial files exist."""
        self.brain_dir.mkdir(parents=True, exist_ok=True)
        
        if not self.task_file.exists():
            self._write_file(self.task_file, self._get_initial_task_content())
            
    def _get_initial_task_content(self) -> str:
        return """# Gas Town Tasks

## Active Tasks
- [ ] Initialize project
"""

    def _write_file(self, path: Path, content: str):
        path.write_text(content, encoding="utf-8")

    def read_task_plan(self) -> List[Dict]:
        """
        Parse task.md and return list of tasks.
        Returns list of dicts: {'status': 'pending'|'done'|'running', 'text': str, 'original_line': str}
        """
        if not self.task_file.exists():
            return []
            
        content = self.task_file.read_text(encoding="utf-8")
        tasks = []
        
        # Regex to find markdown checkboxes: - [ ] or - [x] or - [/]
        # Group 1: x, /, or space. Group 2: Task text
        pattern = r"^\s*[-*]\s*\[([ x/])\]\s*(.+)$"
        
        for line in content.splitlines():
            match = re.match(pattern, line)
            if match:
                marker = match.group(1)
                text = match.group(2).strip()
                
                status = "pending"
                if marker.lower() == "x":
                    status = "done"
                elif marker == "/":
                    status = "running"
                    
                tasks.append({
                    "status": status,
                    "text": text,
                    "original_line": line
                })
                
        return tasks

    def get_next_pending_task(self) -> Optional[str]:
        """Get the first pending task."""
        tasks = self.read_task_plan()
        for t in tasks:
            if t["status"] == "pending":
                return t["text"]
        return None

    def mark_task_status(self, task_text: str, status: str):
        """
        Update local task.md to mark a task as running (/) or done (x).
        status: 'running' or 'done' or 'pending'
        """
        if not self.task_file.exists():
            return

        content = self.task_file.read_text(encoding="utf-8")
        new_lines = []
        
        marker_map = {
            "running": "[/]",
            "done": "[x]",
            "pending": "[ ]"
        }
        marker = marker_map.get(status, "[ ]")
        
        # Simple string matching for now - could be more robust
        # We try to match the exact text.
        for line in content.splitlines():
            # Check if this line is a task and matches our text
            line_match = re.match(r"^\s*[-*]\s*\[([ x/])\]\s*(.+)$", line)
            if line_match:
                current_text = line_match.group(2).strip()
                if current_text == task_text:
                    # Replace the marker
                    # We preserve indentation
                    indent = line[:line.find("-")]
                    new_lines.append(f"{indent}- {marker} {current_text}")
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
                
        self._write_file(self.task_file, "\n".join(new_lines) + "\n")

    def create_new_task(self, title: str, steps: List[str]):
        """Create a new task structure in task.md."""
        content = f"# {title}\n\n## Execution Phase\n"
        for step in steps:
            content += f"- [ ] {step}\n"
        
        content += "\n## Verification Phase\n- [ ] Verify results\n"
        
        self._write_file(self.task_file, content)

    def read_implementation_plan(self) -> str:
        """Read current implementation plan."""
        if not self.plan_file.exists():
            return ""
        return self.plan_file.read_text(encoding="utf-8")

    def init_plan(self, goal: str):
        """Initialize a new implementation plan template."""
        content = f"""# Implementation Plan - {goal}

## Proposed Changes
Describe changes here...

## Verification Plan
How to verify...
"""
        self._write_file(self.plan_file, content)
