import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from control_api import LocalControlHTTPServer, AUTH_TOKEN_ENV


class DummyService:
    def __init__(self) -> None:
        self.name = "test"
        self.path = str(Path(tempfile.gettempdir()))
        self.command = "echo test"
        self.env_path = ""
        self.log_path = ""
        self.health_url = "http://127.0.0.1:1"
        self.service_type = "test"
        self.display_name = "Test Service"
        self.brand_name = "Test Brand"
        self.base_url = ""

    def resolved_path(self):
        return Path(self.path)

    def resolved_env_path(self):
        return None

    def resolved_log_path(self):
        return Path(self.log_path or self.path) / "service.log"


class DummyBackend:
    def __init__(self) -> None:
        self.services = {"test": DummyService()}

    def ordered_services(self):
        return [self.services["test"]]

    def service_status(self, service):
        return "stopped"

    def start_service(self, service):
        return "started"

    def stop_service(self, service):
        return "stopped"

    def restart_service(self, service):
        return "restarted"

    def kill_running_processes(self, service):
        return "killed"
    def reset_service_database(self, service):
        return "db_reset"

    def grant_service_admin(self, service, identifier, by_email=False):
        return f"granted_admin:{identifier}:{'email' if by_email else 'username'}"
    def restart_all_services(self):
        return {"test": "restarted"}

    def kill_all_running_processes(self):
        return {"test": "killed"}

    def discover_services(self, root_path):
        return []

    def add_service(self, service):
        self.services[service.name] = service

    def read_log(self, service, lines=100):
        return "log line"

    def health_status(self, service):
        return "200 OK"

    def run_browser_debug(self, browser_name, target_url, action):
        return {"status": "ok", "browser": browser_name, "url": target_url, "action": action}

    def wait_until_healthy(self, service, timeout=30, interval=1.0):
        return {"status": "healthy", "health": "200 OK"}


class ControlAPITestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = DummyBackend()
        self.server = LocalControlHTTPServer(self.backend, "127.0.0.1", 0)
        self.assertTrue(self.server.start())
        self.base_url = f"http://127.0.0.1:{self.server.port}"
        self.token = "test-token"
        os.environ[AUTH_TOKEN_ENV] = self.token

    def tearDown(self) -> None:
        self.server.stop()
        os.environ.pop(AUTH_TOKEN_ENV, None)

    def test_health_endpoint(self):
        response = requests.get(f"{self.base_url}/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_services_endpoint(self):
        response = requests.get(f"{self.base_url}/services")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["services"][0]["name"], "test")

    def test_start_service_requires_auth(self):
        response = requests.post(f"{self.base_url}/services/test/start")
        self.assertEqual(response.status_code, 403)

    def test_start_service_with_token(self):
        response = requests.post(
            f"{self.base_url}/services/test/start",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"], "started")

    def test_start_service_with_token_query(self):
        response = requests.post(f"{self.base_url}/services/test/start?token={self.token}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"], "started")

    def test_reset_service_database(self):
        response = requests.post(
            f"{self.base_url}/services/test/reset_db",
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            json={},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"], "db_reset")

    def test_grant_service_admin(self):
        response = requests.post(
            f"{self.base_url}/services/test/grant_admin",
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            json={"identifier": "testuser", "by_email": False},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"], "granted_admin:testuser:username")

    def test_browser_debug(self):
        response = requests.post(
            f"{self.base_url}/browser/debug",
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            json={"browser_name": "chromium", "target_url": "http://127.0.0.1:3000", "action": "home"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
