---
description: Spawn and monitor Jules agent swarms in Gas Town
---

# Gas Town Workflow

Use these commands to orchestrate Jules agents from Antigravity IDE.

## Quick Start

```bash
# Initialize workspace (first time only)
gt install ~/gt --git
cd ~/gt

# Add your project
gt rig add myproject https://github.com/you/repo.git

# Start Mayor session
gt mayor attach
```

## Spawning Workers

```bash
# Single task
gt spawn "Fix the login bug" --rig myproject

# Swarm from convoy
gt convoy create "Feature Sprint" --issues "Task 1" "Task 2" "Task 3"
gt swarm --convoy <convoy-id> --count 3
```

## Monitoring

```bash
# Check job status
gt status <job-id>

# Live dashboard (in tmux)
./scripts/monitor_swarm.sh
```

## tmux Layouts

```bash
# Start Gas Town session
tmux -f tmux/gastown.tmux.conf new -s gastown

# Layouts (use Prefix + key):
# Alt+m = Mayor + 2 Polecats
# Alt+s = 2x2 Swarm grid
# Alt+d = Dashboard + 3 Workers
```

## Checkout PR for Review

```bash
# Inspect a polecat's work locally
gt checkout <pr-id>
```
