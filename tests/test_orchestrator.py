import unittest
from types import SimpleNamespace

from openvibe_studio.backend.orchestrator import Orchestrator
from openvibe_studio.models.service import ServiceDefinition


class DummyProcessManager:
    def __init__(self) -> None:
        self.calls = []

    def stop_service(self, service):
        self.calls.append(("stop", service.name))
        return "stopped"

    def start_service(self, service, env):
        self.calls.append(("start", service.name))
        return "started"

    def kill_all_running_processes(self, services):
        return {name: "killed" for name in services}

    def scan_for_lingering_processes(self, services):
        return {name: [] for name in services}


class DummyRegistry:
    def __init__(self, services):
        self.services = services

    def ordered_services(self):
        return list(self.services.values())


class DummyEnvManager:
    def __init__(self) -> None:
        self.loaded = []

    def load_env(self, env_path):
        self.loaded.append(env_path)
        return {}


class OrchestratorTestCase(unittest.TestCase):
    def test_restart_all_services(self):
        service = ServiceDefinition("one", ".", "", "", "", "")
        registry = DummyRegistry({"one": service})
        process_manager = DummyProcessManager()
        env_manager = DummyEnvManager()
        orchestrator = Orchestrator(registry, process_manager, env_manager)

        result = orchestrator.restart_all_services()
        self.assertEqual(result, {"stop-one": "stopped", "start-one": "started"})
        self.assertEqual(process_manager.calls, [("stop", "one"), ("start", "one")])
        self.assertEqual(env_manager.loaded, [service.resolved_env_path()])

    def test_kill_all_running_processes(self):
        service = ServiceDefinition("one", ".", "", "", "", "")
        registry = DummyRegistry({"one": service})
        process_manager = DummyProcessManager()
        env_manager = DummyEnvManager()
        orchestrator = Orchestrator(registry, process_manager, env_manager)

        result = orchestrator.kill_all_running_processes()
        self.assertEqual(result, {"one": "killed"})


if __name__ == "__main__":
    unittest.main()
