"""Load vendor protocol constants from a private HA configuration file."""

from __future__ import annotations

import json
from pathlib import Path

from .protocol.client import PrivateSettings


PRIVATE_FILE = ".fordpass_cn_modern_private.json"


def load_private_settings(config_directory: str) -> PrivateSettings:
    path = Path(config_directory) / PRIVATE_FILE
    if path.stat().st_mode & 0o077:
        raise PermissionError(f"{PRIVATE_FILE} must be accessible only to the HA user")
    return PrivateSettings(**json.loads(path.read_text()))
