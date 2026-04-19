from __future__ import annotations

from typing import Any, Dict


def restart_all_services(backend: Any) -> Dict[str, Any]:
    return {"results": backend.restart_all_services()}


def kill_all_services(backend: Any) -> Dict[str, Any]:
    return {"results": backend.kill_all_running_processes()}
