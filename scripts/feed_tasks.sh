#!/bin/bash
# feed_tasks.sh - Feed tasks to the swarm from various sources
#
# Supports: convoy files, GitHub issues, stdin

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

show_help() {
    cat << EOF
feed_tasks.sh - Feed tasks to the swarm

USAGE:
    feed_tasks.sh [SOURCE] [OPTIONS]

SOURCES:
    --convoy <id>       Feed tasks from a convoy
    --file <path>       Feed tasks from a file (one task per line)
    --github <query>    Feed tasks from GitHub issues (requires gh CLI)
    -                   Read tasks from stdin

OPTIONS:
    --rig <name>        Target rig for all tasks (default: default)
    --count <n>         Maximum number of tasks to feed (default: 4)
    --dry-run           Show what would be done without executing
    -h, --help          Show this help message

EXAMPLES:
    # Feed from convoy
    feed_tasks.sh --convoy convoy-abc123

    # Feed from file
    echo "Fix bug in auth.py" > tasks.txt
    echo "Add unit tests for utils" >> tasks.txt
    feed_tasks.sh --file tasks.txt

    # Feed from GitHub issues
    feed_tasks.sh --github "label:bug is:open" --count 3

    # Feed from stdin
    echo -e "Task 1\nTask 2" | feed_tasks.sh -
EOF
}

# Defaults
SOURCE_TYPE=""
SOURCE=""
RIG="default"
COUNT=4
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        --convoy)
            SOURCE_TYPE="convoy"
            SOURCE="$2"
            shift 2
            ;;
        --file)
            SOURCE_TYPE="file"
            SOURCE="$2"
            shift 2
            ;;
        --github)
            SOURCE_TYPE="github"
            SOURCE="$2"
            shift 2
            ;;
        -)
            SOURCE_TYPE="stdin"
            shift
            ;;
        --rig)
            RIG="$2"
            shift 2
            ;;
        --count)
            COUNT="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

if [[ -z "$SOURCE_TYPE" ]]; then
    log_error "No source specified"
    show_help
    exit 1
fi

# Collect tasks based on source
declare -a TASKS

case "$SOURCE_TYPE" in
    convoy)
        log_info "Loading tasks from convoy: $SOURCE"
        # Would call gastown.py convoy show, for now using Python
        TASKS=($(python3 << PYEOF
import asyncio
import sys
sys.path.insert(0, "$GT_ROOT/lib")
from convoy import ConvoyManager
from config import find_workspace

async def main():
    ws = find_workspace()
    if not ws:
        return
    mgr = ConvoyManager(str(ws))
    tasks = await mgr.get_tasks("$SOURCE")
    for t in tasks[:$COUNT]:
        print(t.get("description", "").replace(" ", "_"))

asyncio.run(main())
PYEOF
        ))
        ;;
    file)
        log_info "Loading tasks from file: $SOURCE"
        if [[ ! -f "$SOURCE" ]]; then
            log_error "File not found: $SOURCE"
            exit 1
        fi
        mapfile -t TASKS < "$SOURCE"
        ;;
    github)
        log_info "Loading tasks from GitHub: $SOURCE"
        if ! command -v gh &> /dev/null; then
            log_error "gh CLI not found. Install GitHub CLI first."
            exit 1
        fi
        TASKS=($(gh issue list --search "$SOURCE" --limit "$COUNT" --json title --jq '.[].title'))
        ;;
    stdin)
        log_info "Reading tasks from stdin..."
        mapfile -t TASKS
        ;;
esac

# Limit to count
TASKS=("${TASKS[@]:0:$COUNT}")

if [[ ${#TASKS[@]} -eq 0 ]]; then
    log_warn "No tasks found"
    exit 0
fi

log_info "Found ${#TASKS[@]} task(s)"

# Feed tasks to swarm
for i in "${!TASKS[@]}"; do
    task="${TASKS[$i]}"
    # Restore spaces
    task="${task//_/ }"
    
    log_info "[$((i+1))/${#TASKS[@]}] $task"
    
    if [[ "$DRY_RUN" == true ]]; then
        echo "  [DRY RUN] Would spawn: $task"
    else
        python3 "${GT_ROOT}/gastown.py" spawn "$task" --rig "$RIG" &
        
        # Small delay to avoid overwhelming the API
        sleep 1
    fi
done

if [[ "$DRY_RUN" == false ]]; then
    log_info "Waiting for spawns to complete..."
    wait
    log_info "All tasks submitted. Use 'monitor_swarm.sh' to track progress."
fi
