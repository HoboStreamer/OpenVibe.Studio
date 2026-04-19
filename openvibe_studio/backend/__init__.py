from __future__ import annotations

from pathlib import Path
from typing import Any
from .service_registry import ServiceRegistry
from .process_manager import ProcessManager
from .log_manager import LogManager
from .env_manager import EnvManager
from .health import HealthManager
from .browser_debug import BrowserDebug
from .orchestrator import Orchestrator
from ..config import BROWSER_DEBUG_DIR
from ..models.service import ServiceDefinition

__all__ = [
    "ServiceRegistry",
    "ProcessManager",
    "LogManager",
    "EnvManager",
    "HealthManager",
    "BrowserDebug",
    "Orchestrator",
    "OpenVibeBackend",
]


class OpenVibeBackend:
    def __init__(self) -> None:
        self.registry = ServiceRegistry()
        self.process_manager = ProcessManager()
        self.log_manager = LogManager()
        self.env_manager = EnvManager()
        self.health_manager = HealthManager()
        self.browser_debug = BrowserDebug(BROWSER_DEBUG_DIR)
        self.orchestrator = Orchestrator(self.registry, self.process_manager, self.env_manager)

    @property
    def services(self) -> dict[str, ServiceDefinition]:
        return self.registry.services

    def add_service(self, service: ServiceDefinition) -> None:
        self.registry.add_service(service)

    def remove_service(self, name: str) -> None:
        self.registry.remove_service(name)

    def start_service(self, service: ServiceDefinition) -> str:
        env = self.env_manager.load_env(service.resolved_env_path())
        return self.process_manager.start_service(service, env)

    def stop_service(self, service: ServiceDefinition) -> str:
        return self.process_manager.stop_service(service)

    def restart_service(self, service: ServiceDefinition) -> str:
        env = self.env_manager.load_env(service.resolved_env_path())
        return self.process_manager.restart_service(service, env)

    def reset_service_database(self, service: ServiceDefinition) -> str:
        env = self.env_manager.load_env(service.resolved_env_path())
        return self.process_manager.reset_service_database(service, env)

    def grant_service_admin(self, service: ServiceDefinition, identifier: str, by_email: bool = False) -> str:
        env = self.env_manager.load_env(service.resolved_env_path())
        return self.process_manager.grant_service_admin(service, identifier, by_email, env)

    def find_running_processes(self, service: ServiceDefinition) -> list:
        return self.process_manager.find_running_processes(service)

    def scan_for_lingering_processes(self) -> dict[str, list]:
        return self.process_manager.scan_for_lingering_processes(self.services)

    def kill_running_processes(self, service: ServiceDefinition) -> str:
        return self.process_manager.kill_running_processes(service)

    def kill_all_running_processes(self) -> dict[str, str]:
        return self.orchestrator.kill_all_running_processes()

    def ordered_services(self) -> list[ServiceDefinition]:
        return self.registry.ordered_services()

    def restart_all_services(self) -> dict[str, str]:
        return self.orchestrator.restart_all_services()

    def browser_test_support(self) -> bool:
        return self.browser_debug.browser_available()

    def run_browser_debug(self, browser_name: str, target_url: str, action: str) -> dict[str, str]:
        return self.browser_debug.run_browser_debug(browser_name, target_url, action)

    def is_service_running(self, name: str) -> bool:
        if self.process_manager.is_service_running(name):
            return True
        service = self.services.get(name)
        if not service:
            return False
        return bool(self.process_manager.find_running_processes(service))

    def service_status(self, service: ServiceDefinition) -> str:
        if self.process_manager.is_service_starting(service.name):
            return "starting"
        if self.is_service_running(service.name):
            return "running"
        return "stopped"

    def health_status(self, service: ServiceDefinition) -> str:
        if not self.is_service_running(service.name):
            return "stopped"
        return self.health_manager.health_status(service.health_url)

    def service_log_stats(self, service: ServiceDefinition) -> tuple[int, int]:
        return self.log_manager.log_stats(service.resolved_log_path())

    def wait_until_healthy(self, service: ServiceDefinition, timeout: int = 30, interval: float = 1.0) -> dict[str, str]:
        return self.health_manager.wait_until_healthy(service.health_url, timeout, interval)

    def load_env_content(self, service: ServiceDefinition) -> str:
        return self.env_manager.load_env_content(service.resolved_env_path() or service.resolved_path() / ".env")

    def save_env_content(self, service: ServiceDefinition, content: str) -> str:
        env_path = Path(service.env_path or service.resolved_path() / ".env")
        self.env_manager.save_env_content(env_path, content)
        return str(env_path)

    def read_log(self, service: ServiceDefinition, lines: int = 100) -> str:
        return self.log_manager.read_log(service.resolved_log_path(), lines)

    def clear_log(self, service: ServiceDefinition) -> bool:
        return self.log_manager.clear_log(service.resolved_log_path())

    def export_log(self, service: ServiceDefinition, destination: str) -> bool:
        return self.log_manager.export_log(service.resolved_log_path(), Path(destination))

    def discover_services(self, root_path: Path) -> dict[str, Any]:
        candidates = self.registry.discover_services(root_path)
        added = 0
        for service in candidates:
            if service.name in self.services:
                continue
            self.add_service(service)
            added += 1
        return {"discovered": len(candidates), "added": added, "services": [service.to_dict() for service in candidates]}
