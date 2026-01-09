# Hook Context Template
# This file is injected as context when spawning a polecat

## Project Overview

**Repository**: {{repo_name}}
**Branch**: {{branch_name}}
**Created**: {{created_at}}

---

## Your Task

{{task_description}}

---

## Context Map

### Key Files
{{#each key_files}}
- `{{this}}`
{{/each}}

### Recent Changes
{{#each recent_changes}}
- {{hash}}: {{message}} ({{when}})
{{/each}}

---

## Constraints

1. Make changes ONLY to the branch: `{{branch_name}}`
2. Create small, focused commits
3. Write tests for new functionality
4. Follow existing code style
5. Update documentation if needed

---

## When Complete

Your changes will be reviewed via Pull Request.
Ensure all tests pass before marking complete.
