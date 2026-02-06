"""Coding tools available to the agent."""

from __future__ import annotations

import os
import subprocess
import glob as glob_module
from pathlib import Path

from agent.providers.base import ToolDef

# --- Tool Definitions (provider-agnostic JSON Schema) ---

TOOL_DEFS: list[ToolDef] = [
    ToolDef(
        name="read_file",
        description="Read the contents of a file. Returns the file content as text.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative or absolute file path"},
            },
            "required": ["path"],
        },
    ),
    ToolDef(
        name="write_file",
        description="Create or overwrite a file with the given content.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write to"},
                "content": {"type": "string", "description": "Full file content"},
            },
            "required": ["path", "content"],
        },
    ),
    ToolDef(
        name="edit_file",
        description="Edit a file by replacing an exact string match with new content. "
                    "The old_string must appear exactly once in the file.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to edit"},
                "old_string": {"type": "string", "description": "Exact text to find (must be unique in file)"},
                "new_string": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_string", "new_string"],
        },
    ),
    ToolDef(
        name="list_files",
        description="List files in a directory. Supports glob patterns.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path or glob pattern (e.g. 'src/**/*.py')"},
            },
            "required": ["path"],
        },
    ),
    ToolDef(
        name="search_files",
        description="Search file contents using a regex pattern. Returns matching lines with file paths.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "Directory to search in (default: working dir)"},
                "include": {"type": "string", "description": "File glob filter (e.g. '*.py')"},
            },
            "required": ["pattern"],
        },
    ),
    ToolDef(
        name="run_command",
        description="Execute a shell command and return stdout/stderr. Use for running tests, "
                    "installing packages, git operations, etc.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30)"},
            },
            "required": ["command"],
        },
    ),
    ToolDef(
        name="task_complete",
        description="Signal that the task is finished. Call this when you have completed the user's request.",
        parameters={
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Brief summary of what was accomplished"},
            },
            "required": ["summary"],
        },
    ),
]


class ToolRegistry:
    """Executes tools within a working directory."""

    def __init__(self, working_dir: str):
        self.working_dir = os.path.abspath(working_dir)

    @property
    def definitions(self) -> list[ToolDef]:
        return TOOL_DEFS

    def execute(self, name: str, arguments: dict) -> str:
        """Execute a tool and return the result as a string."""
        try:
            handler = getattr(self, f"_tool_{name}", None)
            if handler is None:
                return f"Error: Unknown tool '{name}'"
            return handler(**arguments)
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"

    def _resolve_path(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.join(self.working_dir, path)

    def _tool_read_file(self, path: str) -> str:
        resolved = self._resolve_path(path)
        if not os.path.isfile(resolved):
            return f"Error: File not found: {path}"
        with open(resolved, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if len(content) > 100_000:
            return content[:100_000] + f"\n\n... (truncated, file is {len(content):,} chars)"
        return content

    def _tool_write_file(self, path: str, content: str) -> str:
        resolved = self._resolve_path(path)
        os.makedirs(os.path.dirname(resolved) or ".", exist_ok=True)
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Wrote {len(content):,} chars to {path}"

    def _tool_edit_file(self, path: str, old_string: str, new_string: str) -> str:
        resolved = self._resolve_path(path)
        if not os.path.isfile(resolved):
            return f"Error: File not found: {path}"
        with open(resolved, "r", encoding="utf-8") as f:
            content = f.read()
        count = content.count(old_string)
        if count == 0:
            return "Error: old_string not found in file"
        if count > 1:
            return f"Error: old_string found {count} times, must be unique. Add more context."
        new_content = content.replace(old_string, new_string, 1)
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(new_content)
        return f"Edited {path}: replaced 1 occurrence"

    def _tool_list_files(self, path: str) -> str:
        resolved = self._resolve_path(path)
        if "*" in path or "?" in path:
            matches = sorted(glob_module.glob(resolved, recursive=True))
            if not matches:
                return "No files matched the pattern."
            rel = [os.path.relpath(m, self.working_dir) for m in matches]
            return "\n".join(rel[:500])

        if os.path.isdir(resolved):
            entries = sorted(os.listdir(resolved))
            result = []
            for e in entries[:500]:
                full = os.path.join(resolved, e)
                suffix = "/" if os.path.isdir(full) else ""
                result.append(e + suffix)
            return "\n".join(result)

        return f"Error: Not a directory or pattern: {path}"

    def _tool_search_files(self, pattern: str, path: str = "", include: str = "") -> str:
        search_dir = self._resolve_path(path) if path else self.working_dir
        cmd = ["grep", "-rn", "--include", include, "-E", pattern, search_dir] if include else \
              ["grep", "-rn", "-E", pattern, search_dir]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            output = result.stdout.strip()
            if not output:
                return "No matches found."
            lines = output.split("\n")
            if len(lines) > 100:
                return "\n".join(lines[:100]) + f"\n... ({len(lines)} total matches)"
            return output
        except subprocess.TimeoutExpired:
            return "Error: Search timed out"

    def _tool_run_command(self, command: str, timeout: int = 30) -> str:
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=min(timeout, 120), cwd=self.working_dir,
            )
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                output += ("\n" if output else "") + result.stderr
            if result.returncode != 0:
                output += f"\n(exit code: {result.returncode})"
            return output.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout}s"

    def _tool_task_complete(self, summary: str) -> str:
        return summary
