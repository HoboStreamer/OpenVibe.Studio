from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def discover_services(backend: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    path_value = payload.get("path")
    if not path_value:
        return {"error": "path is required"}
    return backend.discover_services(Path(path_value))
