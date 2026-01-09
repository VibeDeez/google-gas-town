#!/bin/bash
# monitor_swarm.sh - Monitor all active Jules agents
#
# Displays a live dashboard of agent status with rate limit handling

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# Configuration
POLL_INTERVAL=${POLL_INTERVAL:-5}
MAX_RETRIES=${MAX_RETRIES:-3}
BACKOFF_TIME=${BACKOFF_TIME:-30}

log_info() { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[$(date +%H:%M:%S)]${NC} $1"; }
log_error() { echo -e "${RED}[$(date +%H:%M:%S)]${NC} $1"; }

show_help() {
    cat << EOF
monitor_swarm.sh - Monitor all active Jules agents

USAGE:
    monitor_swarm.sh [OPTIONS]

OPTIONS:
    --interval <s>      Poll interval in seconds (default: 5)
    --once              Show status once and exit
    --json              Output JSON format
    -h, --help          Show this help message

ENVIRONMENT:
    POLL_INTERVAL       Poll interval in seconds
    MAX_RETRIES         Max retries on error before giving up
    BACKOFF_TIME        Backoff time on rate limit (seconds)
EOF
}

# Parse arguments
ONCE=false
JSON_OUTPUT=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        --interval)
            POLL_INTERVAL="$2"
            shift 2
            ;;
        --once)
            ONCE=true
            shift
            ;;
        --json)
            JSON_OUTPUT=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Header
print_header() {
    clear
    echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  🐝 SWARM MONITOR - Google Gas Town${NC}"
    echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# Status line with spinner
SPINNER_CHARS='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
SPINNER_IDX=0

get_spinner() {
    echo "${SPINNER_CHARS:SPINNER_IDX:1}"
    SPINNER_IDX=$(( (SPINNER_IDX + 1) % ${#SPINNER_CHARS} ))
}

# Print agent status
print_agent_status() {
    local job_id="$1"
    local status="$2"
    local task="$3"
    local step="$4"
    
    local icon=""
    local color=""
    
    case "$status" in
        PENDING)
            icon="⏳"
            color="$YELLOW"
            ;;
        RUNNING)
            icon="$(get_spinner)"
            color="$BLUE"
            ;;
        COMPLETED)
            icon="✅"
            color="$GREEN"
            ;;
        FAILED)
            icon="❌"
            color="$RED"
            ;;
        RATE_LIMITED)
            icon="⚠️"
            color="$YELLOW"
            ;;
        *)
            icon="❓"
            color="$NC"
            ;;
    esac
    
    printf "  ${icon} ${color}%-12s${NC} %-30s %s\n" \
        "${job_id:0:12}" \
        "${task:0:30}" \
        "${step:0:25}"
}

# Main monitoring loop
monitor_loop() {
    local error_count=0
    
    while true; do
        print_header
        
        echo -e "${BOLD}  Agent ID      Task                           Current Step${NC}"
        echo "  ────────────  ──────────────────────────────  ─────────────────────────"
        
        # Get active jobs from Gas Town
        # This would typically call 'gt agents' or similar
        # For now, we simulate by checking the .gastown state
        
        WORKSPACE=$(python3 -c "from lib.config import find_workspace; w=find_workspace(); print(w if w else '')" 2>/dev/null || echo "")
        
        if [[ -z "$WORKSPACE" ]]; then
            echo "  No active workspace found. Run 'gt install' first."
        else
            # Read active jobs from hooks
            HOOKS_FILE="${WORKSPACE}/.gastown/beads/beads.json"
            
            if [[ -f "$HOOKS_FILE" ]]; then
                # Parse and display active beads
                python3 << PYEOF
import json
from datetime import datetime

try:
    with open("$HOOKS_FILE") as f:
        data = json.load(f)
    
    beads = data.get("beads", [])
    active = [b for b in beads if b.get("status") == "active"]
    
    if not active:
        print("  No active agents")
    else:
        for bead in active:
            print(f"  🔄 {bead.get('id', 'unknown')[:12]:12} {bead.get('branch_name', '')[:30]:30} Active")
except Exception as e:
    print(f"  Error reading state: {e}")
PYEOF
            else
                echo "  No active agents"
            fi
        fi
        
        echo ""
        echo "  ────────────────────────────────────────────────────────────────"
        echo -e "  ${CYAN}Polling every ${POLL_INTERVAL}s | Ctrl+C to exit${NC}"
        echo -e "  ${CYAN}Time: $(date +%H:%M:%S)${NC}"
        
        if [[ "$ONCE" == true ]]; then
            exit 0
        fi
        
        sleep "$POLL_INTERVAL"
    done
}

# Handle Ctrl+C gracefully
trap 'echo -e "\n\n${GREEN}Monitor stopped.${NC}"; exit 0' INT

# Run
if [[ "$JSON_OUTPUT" == true ]]; then
    # JSON mode - single output
    python3 "${GT_ROOT}/gastown.py" agents --format json 2>/dev/null || echo '{"agents": []}'
else
    monitor_loop
fi
