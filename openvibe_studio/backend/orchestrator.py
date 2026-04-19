from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

import psutil

from ..models.service import ServiceDefinition
from .env_manager import EnvManager
from .process_manager import ProcessManager
from .service_registry import ServiceRegistry


class Orchestrator:
    def __init__(self, registry: ServiceRegistry, process_manager: ProcessManager, env_manager: EnvManager) -> None:
        self.registry = registry
        self.process_manager = process_manager
        self.env_manager = env_manager

    def restart_all_services(self) -> Dict[str, str]:
        results: Dict[str, str] = {}
        ordered_services = self.registry.ordered_services()
        for service in reversed(ordered_services):
            results[f"stop-{service.name}"] = self.process_manager.stop_service(service)

        if not ordered_services:
            return results

        max_workers = min(8, len(ordered_services))
        futures = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for service in ordered_services:
                futures[executor.submit(self._start_service_with_env, service)] = service.name

            completed_results: dict[str, str] = {}
            for future in as_completed(futures):
                service_name = futures[future]
                try:
                    completed_results[service_name] = future.result()
                except Exception as exc:
                    completed_results[service_name] = f"error:{exc}"

        for service in ordered_services:
            results[f"start-{service.name}"] = completed_results.get(service.name, "error:unknown")

        return results

    def _start_service_with_env(self, service: ServiceDefinition) -> str:
        env = self.env_manager.load_env(service.resolved_env_path())
        return self.process_manager.start_service(service, env)

    def kill_all_running_processes(self) -> Dict[str, str]:
        return self.process_manager.kill_all_running_processes(self.registry.services)

    def scan_for_lingering_processes(self) -> Dict[str, List[psutil.Process]]:
        return self.process_manager.scan_for_lingering_processes(self.registry.services)
