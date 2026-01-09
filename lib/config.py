"""
Configuration management for Gas Town.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Optional


DEFAULT_CONFIG = {
    "workspace": "~/gt",
    "default_agent": "jules",
    "poll_interval": 5,
    "max_concurrent_agents": 4,
    "rate_limit_backoff": 30,
    "auth": {
        "method": "adc",  # adc, gcloud, token
        "token_path": None
    },
    "tmux": {
        "session_name": "gastown",
        "layout": "default"
    }
}


def find_workspace() -> Optional[Path]:
    """Find the Gas Town workspace by searching up from current directory."""
    current = Path.cwd()
    
    while current != current.parent:
        if (current / ".gastown").exists():
            return current
        current = current.parent
    
    # Check default location
    default = Path.home() / "gt"
    if (default / ".gastown").exists():
        return default
    
    return None


def load_config(workspace: Optional[Path] = None) -> Dict:
    """
    Load configuration from workspace.
    
    Searches for .gastown/config.yaml in:
    1. Provided workspace path
    2. Current directory (searching up)
    3. ~/gt (default location)
    """
    if workspace is None:
        workspace = find_workspace()
    
    if workspace is None:
        return DEFAULT_CONFIG.copy()
    
    config_path = Path(workspace) / ".gastown" / "config.yaml"
    
    if not config_path.exists():
        return {**DEFAULT_CONFIG, "workspace": str(workspace)}
    
    try:
        with open(config_path) as f:
            user_config = yaml.safe_load(f) or {}
        
        # Merge with defaults
        config = {**DEFAULT_CONFIG, **user_config}
        config["workspace"] = str(workspace)
        return config
        
    except (yaml.YAMLError, IOError):
        return {**DEFAULT_CONFIG, "workspace": str(workspace)}


def save_config(path: Path, config: Dict):
    """Save configuration to a YAML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def get_auth_config() -> Dict:
    """Get authentication configuration."""
    config = load_config()
    return config.get("auth", DEFAULT_CONFIG["auth"])


def check_auth() -> tuple[bool, str]:
    """
    Check if authentication is properly configured.
    
    Returns:
        Tuple of (is_valid, message)
    """
    auth = get_auth_config()
    method = auth.get("method", "adc")
    
    if method == "adc":
        # Check for Application Default Credentials
        adc_path = os.environ.get(
            "GOOGLE_APPLICATION_CREDENTIALS",
            os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
        )
        if os.path.exists(adc_path):
            return True, "Using Application Default Credentials"
        return False, "Run 'gcloud auth application-default login'"
    
    elif method == "gcloud":
        # Check for gcloud auth
        import subprocess
        try:
            result = subprocess.run(
                ["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                return True, f"Using gcloud account: {result.stdout.strip()}"
            return False, "Run 'gcloud auth login'"
        except FileNotFoundError:
            return False, "gcloud CLI not found. Install Google Cloud SDK."
    
    elif method == "token":
        token_path = auth.get("token_path")
        if token_path and os.path.exists(os.path.expanduser(token_path)):
            return True, f"Using token from {token_path}"
        return False, "Token file not found"
    
    return False, f"Unknown auth method: {method}"
