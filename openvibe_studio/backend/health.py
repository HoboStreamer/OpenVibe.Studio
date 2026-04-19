from __future__ import annotations

import time
from typing import Dict

import requests


class HealthManager:
    def health_status(self, health_url: str) -> str:
        if not health_url:
            return "no health url"
        try:
            response = requests.get(health_url, timeout=3)
            return f"{response.status_code} {response.reason}"
        except Exception as exc:
            return f"error: {exc}"

    def wait_until_healthy(self, health_url: str, timeout: int = 30, interval: float = 1.0) -> Dict[str, str]:
        if not health_url:
            return {"status": "error", "message": "no health url configured"}
        deadline = time.time() + timeout
        last_status = ""
        while time.time() <= deadline:
            try:
                response = requests.get(health_url, timeout=3)
                last_status = f"{response.status_code} {response.reason}"
                if response.status_code == 200:
                    return {"status": "healthy", "health": last_status}
            except Exception as exc:
                last_status = f"error: {exc}"
            time.sleep(interval)
        return {"status": "timeout", "health": last_status}
