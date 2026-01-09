#!/bin/bash
# setup.sh - One-line installer for Google Gas Town
#
# Usage: curl -sSL https://raw.githubusercontent.com/you/google-gas-town/main/setup.sh | bash
#        or: ./setup.sh [--workspace <path>]

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[✓]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[!]${NC} $1"; }
log_error() { echo -e "${RED}[✗]${NC} $1"; }
log_step() { echo -e "${BLUE}[→]${NC} $1"; }

# Header
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║     🏗  Google Gas Town - Multi-Agent Orchestrator   ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

# Parse arguments
WORKSPACE="${HOME}/gt"
SKIP_DEPS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --workspace|-w)
            WORKSPACE="$2"
            shift 2
            ;;
        --skip-deps)
            SKIP_DEPS=true
            shift
            ;;
        -h|--help)
            echo "Usage: setup.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --workspace, -w <path>  Workspace path (default: ~/gt)"
            echo "  --skip-deps             Skip dependency checks"
            echo "  -h, --help              Show this help"
            exit 0
            ;;
        *)
            shift
            ;;
    esac
done

# ============================================================================
# Prerequisites Check
# ============================================================================

log_step "Checking prerequisites..."

MISSING_DEPS=()

# Python 3.8+
if command -v python3 &> /dev/null; then
    PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    log_info "Python ${PY_VERSION} found"
else
    MISSING_DEPS+=("python3 (3.8+)")
fi

# Git 2.25+
if command -v git &> /dev/null; then
    GIT_VERSION=$(git --version | awk '{print $3}')
    log_info "Git ${GIT_VERSION} found"
else
    MISSING_DEPS+=("git (2.25+)")
fi

# tmux 3.0+
if command -v tmux &> /dev/null; then
    TMUX_VERSION=$(tmux -V | awk '{print $2}')
    log_info "tmux ${TMUX_VERSION} found"
else
    log_warn "tmux not found (optional but recommended)"
fi

# Jules CLI
if command -v jules &> /dev/null; then
    log_info "jules CLI found"
else
    log_warn "jules CLI not found"
    echo -e "        Install from: ${BLUE}https://jules.dev/docs/cli${NC}"
fi

# gcloud (for auth)
if command -v gcloud &> /dev/null; then
    log_info "gcloud CLI found"
else
    log_warn "gcloud CLI not found (needed for authentication)"
fi

# Check for missing required dependencies
if [[ ${#MISSING_DEPS[@]} -gt 0 ]] && [[ "$SKIP_DEPS" != true ]]; then
    log_error "Missing required dependencies:"
    for dep in "${MISSING_DEPS[@]}"; do
        echo -e "        - $dep"
    done
    exit 1
fi

# ============================================================================
# Authentication Check
# ============================================================================

log_step "Checking authentication..."

AUTH_OK=false

# Check Application Default Credentials
ADC_PATH="${GOOGLE_APPLICATION_CREDENTIALS:-$HOME/.config/gcloud/application_default_credentials.json}"
if [[ -f "$ADC_PATH" ]]; then
    log_info "Application Default Credentials found"
    AUTH_OK=true
fi

# Check gcloud auth
if [[ "$AUTH_OK" != true ]] && command -v gcloud &> /dev/null; then
    ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null || echo "")
    if [[ -n "$ACTIVE_ACCOUNT" ]]; then
        log_info "Authenticated as: ${ACTIVE_ACCOUNT}"
        AUTH_OK=true
    fi
fi

if [[ "$AUTH_OK" != true ]]; then
    log_warn "No authentication found. Run one of:"
    echo -e "        ${BLUE}gcloud auth login${NC}"
    echo -e "        ${BLUE}gcloud auth application-default login${NC}"
fi

# ============================================================================
# Installation
# ============================================================================

log_step "Installing Google Gas Town..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# If running from curl, we need to clone
if [[ ! -f "${SCRIPT_DIR}/gastown.py" ]]; then
    log_step "Cloning repository..."
    INSTALL_DIR="${HOME}/.gastown-cli"
    
    if [[ -d "$INSTALL_DIR" ]]; then
        log_info "Updating existing installation..."
        cd "$INSTALL_DIR" && git pull --quiet
    else
        git clone --quiet https://github.com/you/google-gas-town.git "$INSTALL_DIR"
    fi
    
    SCRIPT_DIR="$INSTALL_DIR"
fi

# Install Python dependencies
log_step "Installing Python dependencies..."
cd "$SCRIPT_DIR"

if [[ -f "requirements.txt" ]]; then
    pip3 install --quiet -r requirements.txt 2>/dev/null || {
        log_warn "pip install failed, trying with --user"
        pip3 install --quiet --user -r requirements.txt
    }
    log_info "Python dependencies installed"
fi

# Create workspace
log_step "Creating workspace at ${WORKSPACE}..."
python3 "${SCRIPT_DIR}/gastown.py" install "$WORKSPACE" --git 2>/dev/null || {
    log_error "Failed to create workspace"
    exit 1
}

# Create symlink for 'gt' command
log_step "Setting up 'gt' command..."
GT_LINK="/usr/local/bin/gt"

if [[ -w "/usr/local/bin" ]]; then
    ln -sf "${SCRIPT_DIR}/gastown.py" "$GT_LINK" 2>/dev/null || true
    chmod +x "$GT_LINK" 2>/dev/null || true
    log_info "'gt' command available"
else
    # Try user bin directory
    USER_BIN="${HOME}/.local/bin"
    mkdir -p "$USER_BIN"
    ln -sf "${SCRIPT_DIR}/gastown.py" "${USER_BIN}/gt"
    chmod +x "${USER_BIN}/gt"
    
    if [[ ":$PATH:" != *":$USER_BIN:"* ]]; then
        log_warn "Add to your PATH: export PATH=\"\$PATH:${USER_BIN}\""
    else
        log_info "'gt' command available"
    fi
fi

# Make scripts executable
chmod +x "${SCRIPT_DIR}/scripts/"*.sh 2>/dev/null || true

# ============================================================================
# Summary
# ============================================================================

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║              ✓ Installation Complete!                ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Workspace:${NC} $WORKSPACE"
echo ""
echo -e "${BOLD}Quick Start:${NC}"
echo -e "  1. ${BLUE}cd ${WORKSPACE}${NC}"
echo -e "  2. ${BLUE}gt rig add myproject https://github.com/you/repo.git${NC}"
echo -e "  3. ${BLUE}gt mayor attach${NC}"
echo ""
echo -e "${BOLD}For Antigravity IDE:${NC}"
echo -e "  Open terminal and run: ${BLUE}tmux -f ${SCRIPT_DIR}/tmux/gastown.tmux.conf new -s gastown${NC}"
echo ""
echo -e "${BOLD}Documentation:${NC} ${BLUE}https://github.com/you/google-gas-town#readme${NC}"
echo ""
