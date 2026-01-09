# Jules Task Prompt Template
# Standard prompt structure for Jules agent tasks

## Task

{{task_description}}

## Repository Context

You are working on branch `{{branch_name}}` in repository `{{repo_name}}`.

### Files to Focus On
{{#if context_files}}
{{#each context_files}}
- `{{this}}`
{{/each}}
{{else}}
No specific files provided. Please explore the codebase as needed.
{{/if}}

### Project Structure
```
{{file_tree}}
```

## Instructions

1. **Understand First**: Read relevant files before making changes
2. **Plan**: Outline your approach before writing code
3. **Implement**: Make focused, incremental changes
4. **Test**: Ensure your changes work correctly
5. **Document**: Update docs/comments as needed

## Constraints

- Stay focused on the assigned task
- Follow the project's coding conventions
- Write meaningful commit messages
- Create a Pull Request when complete

## Output

When finished, provide:
1. Summary of changes made
2. Files modified
3. Any issues encountered
4. Suggestions for follow-up work (if any)
