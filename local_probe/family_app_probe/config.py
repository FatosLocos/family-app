import json
from pathlib import Path


CONFIG_PATH = Path.home() / ".config" / "family-app-probe" / "config.json"


def load_config():
    return json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}


def save_config(config):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")
    CONFIG_PATH.chmod(0o600)
