#!/bin/bash
# spawn_polecat.sh - Spawn a single Jules polecat worker
#
# Usage: spawn_polecat.sh <task> [--rig <rig>] [--files <file1,file2>]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

show_help() {
    cat << EOF
spawn_polecat.sh - Spawn a single Jules polecat worker

USAGE:
    spawn_polecat.sh <task> [OPTIONS]

ARGUMENTS:
    <task>              Task description or issue ID

OPTIONS:
    --rig <name>        Target rig (default: default)
    --files <list>      Comma-separated list of context files
    --branch <name>     Custom branch name (auto-generated if not provided)
    --watch             Watch job until completion
    -h, --help          Show this help message

EXAMPLES:
    spawn_polecat.sh "Fix the login bug in auth.py"
    spawn_polecat.sh "Add unit tests" --rig myproject --watch
    spawn_polecat.sh "#123" --files src/main.py,src/utils.py
EOF
}

# Parse arguments
TASK=""
RIG="default"
FILES=""
BRANCH=""
WATCH=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        --rig)
            RIG="$2"
            shift 2
            ;;
        --files)
            FILES="$2"
            shift 2
            ;;
        --branch)
            BRANCH="$2"
            shift 2
            ;;
        --watch)
            WATCH=true
            shift
            ;;
        *)
            if [[ -z "$TASK" ]]; then
                TASK="$1"
            fi
            shift
            ;;
    esac
done

if [[ -z "$TASK" ]]; then
    log_error "Task is required"
    show_help
    exit 1
fi

# Check auth
log_info "Checking authentication..."
if ! command -v jules &> /dev/null; then
    log_error "jules CLI not found. Install Jules Agent CLI first."
    exit 1
fi

# Build spawn command
CMD="python3 ${GT_ROOT}/gastown.py spawn \"$TASK\" --rig $RIG"

if [[ -n "$FILES" ]]; then
    IFS=',' read -ra FILE_ARRAY <<< "$FILES"
    for file in "${FILE_ARRAY[@]}"; do
        CMD="$CMD --files $file"
    done
fi

log_info "Spawning polecat for: $TASK"
log_info "Rig: $RIG"

# Execute
eval "$CMD"

if [[ "$WATCH" == true ]]; then
    log_info "Watching job... (Ctrl+C to stop)"
    # The gastown.py spawn command outputs job ID, we could parse and watch
    # For now, suggest using the status command
    log_info "Use 'gt status <job_id>' to check progress"
fi
