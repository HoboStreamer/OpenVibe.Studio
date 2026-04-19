from __future__ import annotations

from typing import Any, Dict


def browser_debug(backend: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    browser_name = payload.get("browser_name") or payload.get("browser")
    target_url = payload.get("target_url") or payload.get("url")
    action = payload.get("action")
    if not browser_name or not target_url or not action:
        return {"error": "browser_name, target_url, and action are required"}
    return backend.run_browser_debug(browser_name, target_url, action)
