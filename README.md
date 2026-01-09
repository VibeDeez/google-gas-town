# 🏗 Google Gas Town

**Multi-Agent Workspace Manager for Antigravity IDE & Jules Agent CLI**

A port of [Steve Yegge's Gas Town](https://github.com/steveyegge/gastown) orchestration system, adapted for the Google ecosystem.

---

## Overview

Google Gas Town coordinates multiple Jules agents working on different tasks. Instead of losing context when agents restart, Gas Town persists work state in git-backed hooks, enabling reliable multi-agent workflows.

```
┌─────────────────────────────────────────────────────────────┐
│                     🎩 THE MAYOR                            │
│                   (AI Coordinator)                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
│   │ 🦨 P1   │  │ 🦨 P2   │  │ 🦨 P3   │  │ 🦨 P4   │       │
│   │ Polecat │  │ Polecat │  │ Polecat │  │ Polecat │       │
│   └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘       │
│        │            │            │            │             │
│        ▼            ▼            ▼            ▼             │
│   ┌─────────────────────────────────────────────────┐      │
│   │        📿 BEADS (Git-backed Memory)             │      │
│   │    Context Maps • Branch Pointers • PRs         │      │
│   └─────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

## Features

- **Async Architecture**: Non-blocking orchestration with `asyncio` for concurrent agent management
- **Jules CLI Integration**: Native support for Jules' async job submission/polling pattern
- **Beads Memory**: Git-backed state with context maps (not compression) for Gemini's large context window
- **Swarm Dashboard**: Rich-based live UI with agent status spinners
- **tmux Integration**: Antigravity IDE-optimized layouts and keybindings
- **Rate Limit Handling**: Automatic backoff when hitting API quotas
- **🧤 White Glove Mode**: User-friendly TUI that hides all terminal complexity

---

## 🧤 White Glove Mode (Recommended)

**Skip the complexity.** No tmux, no keyboard shortcuts, no terminal management.

```bash
gt glove
```

That's it. Just type what you want:

```
┌──────────────────────────────────────────────────────────────┐
│  🏗 GAS TOWN  ›  myproject                    Workers: idle  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  What would you like to do?                                  │
│  › Fix the authentication bug that's breaking login_        │
│                                                              │
│  Enter: send • Tab: suggest • Esc: menu • Ctrl+C: exit       │
├──────────────────────────────────────────────────────────────┤
│  🐝 Swarm Status                                             │
│  ──────────────                                              │
│  🔄 polecat-a3f2   Fix auth bug...        running    45s     │
│  ✅ polecat-b7c1   Add rate limiting      complete   PR #42  │
└──────────────────────────────────────────────────────────────┘
```

**Features:**
- Natural language input — just describe what you want
- Real-time status — see all workers without switching windows
- Auto task breakdown — "Fix X and add tests" spawns 2 workers
- Zero commands to memorize — just Enter, Tab, Esc

---

## Quick Start

### Prerequisites

- Python 3.8+
- Git 2.25+ (for worktree support)
- [Jules CLI](https://jules.dev/docs/cli)
- tmux 3.0+ (recommended)
- gcloud CLI (for authentication)

### Installation

```bash
# Clone the repository
git clone https://github.com/you/google-gas-town.git
cd google-gas-town

# Run the installer
./setup.sh

# Or install manually:
pip install -r requirements.txt
```

### Initialize Workspace

```bash
# Create your Gas Town workspace
gt install ~/gt --git
cd ~/gt

# Add your first project
gt rig add myproject https://github.com/you/repo.git
```

### Start the Mayor

```bash
# Launch the Mayor (your AI coordinator)
gt mayor attach
```

The Mayor is your primary interface. Tell it what you want to accomplish, and it will:
1. Break down tasks
2. Create convoys
3. Spawn polecat workers
4. Monitor progress
5. Summarize results

---

## Core Concepts

| Concept | Description |
|---------|-------------|
| **🎩 Mayor** | AI coordinator that orchestrates all work |
| **🏗 Rig** | Project container wrapping a git repository |
| **🦨 Polecat** | Ephemeral worker agent (spawns, completes task, disappears) |
| **🪝 Hook** | Git worktree for persistent agent work |
| **🚚 Convoy** | Bundle of related tasks for distribution |
| **📿 Beads** | Git-backed memory with context maps |

---

## Commands Reference

### Workspace Management

```bash
gt install <path>           # Initialize workspace
gt rig add <name> <repo>    # Add project
gt rig list                 # List projects
```

### Agent Operations

```bash
gt spawn <task> --rig <rig>         # Spawn single worker
gt swarm --convoy <id> --count N    # Spawn N concurrent workers
gt status <job_id>                  # Check job status
gt checkout <pr_id>                 # Checkout PR locally
```

### Convoy (Work Tracking)

```bash
gt convoy create <name> --issues "Task 1" "Task 2"
gt convoy status <id>
```

### Mayor Session

```bash
gt mayor attach             # Start interactive session

# Inside Mayor session:
/spawn <task>              # Spawn worker
/swarm <convoy_id>         # Launch convoy
/status                    # Show dashboard
/quit                      # Exit
```

---

## Running in Antigravity IDE

### Option 1: Integrated Terminal

1. Open Antigravity IDE
2. Open the integrated terminal
3. Start a tmux session with Gas Town config:

```bash
tmux -f path/to/tmux/gastown.tmux.conf new -s gastown
```

### Option 2: tmux Layouts

Use keyboard shortcuts (Prefix = Ctrl+B by default):

| Shortcut | Layout |
|----------|--------|
| `Prefix` + `Alt+m` | Mayor + 2 Polecats |
| `Prefix` + `Alt+s` | 2x2 Swarm grid |
| `Prefix` + `Alt+d` | Dashboard + 3 Workers |
| `Prefix` + `S` | Sync all panes (broadcast) |

### Option 3: Use the Workflow

If workflow is configured in your Antigravity workspace:

```
/gastown
```

This will show available Gas Town commands.

---

## Architecture Details

### Async Mismatch Solution

Unlike Claude Code's synchronous/interactive loop, Jules uses async jobs. Gas Town handles this with:

```python
# The Mayor runs an asyncio event loop
async def interactive_loop(self):
    while running:
        # Non-blocking input
        user_input = await get_input_async()
        
        # Concurrent job polling
        await check_job_updates()
        
        # Process commands
        await process_command(user_input)
```

### Beads as Branch Managers

Gas Town's Beads are **remote branch pointers**, not just local git state:

- When a Polecat finishes → Bead captures the diff
- `checkout_pr_locally()` → Instantly inspect work in IDE
- Context Maps → Structured repo navigation for Gemini

### Rate Limit Protection

```python
if status.state == "RATE_LIMITED":
    await asyncio.sleep(config.rate_limit_backoff)
    continue
```

---

## Configuration

Edit `config.yaml` or workspace `.gastown/config.yaml`:

```yaml
max_concurrent_agents: 4
poll_interval: 5
rate_limit_backoff: 30

auth:
  method: adc  # adc | gcloud | token

beads:
  context_map: true
```

---

## Troubleshooting

### Authentication Failed

```bash
# Use Application Default Credentials
gcloud auth application-default login

# Or regular gcloud auth
gcloud auth login
```

### Jules CLI Not Found

Install the Jules Agent CLI from: https://jules.dev/docs/cli

### Rate Limiting

If you see rate limit errors:
1. Reduce `max_concurrent_agents` in config
2. Increase `rate_limit_backoff`
3. Check your API quota

### tmux Issues in Antigravity

Ensure your terminal supports:
- 256 colors
- Mouse events
- UTF-8

---

## File Structure

```
google-gas-town/
├── gastown.py              # Main CLI (asyncio-based)
├── setup.sh                # One-line installer
├── config.yaml             # Default configuration
├── requirements.txt        # Python dependencies
│
├── lib/
│   ├── mayor.py            # Mayor coordinator
│   ├── jules_wrapper.py    # Async Jules CLI wrapper
│   ├── dashboard.py        # Rich-based swarm UI
│   ├── beads.py            # Memory/context maps
│   ├── hooks.py            # Git worktree persistence
│   ├── polecat.py          # Ephemeral workers
│   ├── rig.py              # Project containers
│   ├── convoy.py           # Task bundles
│   └── config.py           # Config management
│
├── scripts/
│   ├── spawn_polecat.sh    # Spawn single worker
│   ├── monitor_swarm.sh    # Live dashboard
│   └── feed_tasks.sh       # Task distribution
│
├── tmux/
│   ├── gastown.tmux.conf   # IDE-optimized config
│   └── layouts/            # Layout definitions
│
├── templates/              # Task/convoy templates
└── .agent/workflows/       # Antigravity integration
```

---

## License

MIT License - See [LICENSE](LICENSE) for details.

---

## Credits

Based on [Gas Town](https://github.com/steveyegge/gastown) by Steve Yegge.
Adapted for Google Antigravity IDE and Jules Agent CLI.
