"""Read this client's rendered deployment input without server tooling imports."""

import json
import os
from pathlib import Path


def load():
    path = os.environ.get("MODULE_CONFIG")
    config = json.loads(Path(path).read_text()) if path else {}
    if config.get("module_id", "admin_web") != "admin_web":
        raise ValueError("MODULE_CONFIG must belong to admin_web")
    options = config.get("settings", {})
    port = int(os.environ.get("ADMIN_WEB_PORT", config.get("port", 18765)))
    if not 1024 <= port <= 65535:
        raise ValueError("Local companion port must be 1024–65535")
    default_root = (
        Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share")))
        / "OpenCodeCloudWeb"
    )
    return {
        "port": port,
        "data_root": os.environ.get(
            "ADMIN_WEB_DATA_ROOT", config.get("data_root", str(default_root))
        ),
        "gateway_url": os.environ.get(
            "ADMIN_WEB_GATEWAY_URL",
            options.get("gateway_url", "http://127.0.0.1:18080"),
        ),
    }
