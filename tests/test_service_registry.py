import json
import os
import tempfile
import unittest
from pathlib import Path

from openvibe_studio.backend.service_registry import ServiceRegistry
from openvibe_studio.models.service import ServiceDefinition
import openvibe_studio.backend.service_registry as service_registry


class ServiceRegistryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp()
        os.close(fd)
        self.config_path = Path(path)
        self.original_config = service_registry.CONFIG_FILE
        service_registry.CONFIG_FILE = self.config_path
        if self.config_path.exists():
            self.config_path.unlink()

    def tearDown(self) -> None:
        service_registry.CONFIG_FILE = self.original_config
        if self.config_path.exists():
            self.config_path.unlink()

    def test_save_and_load_services(self):
        registry = ServiceRegistry()
        service = ServiceDefinition(
            name="test-service",
            path=str(Path(tempfile.mkdtemp())),
            command="echo test",
            env_path="",
            log_path="",
            health_url="",
        )
        registry.add_service(service)
        self.assertIn("test-service", registry.services)

        reloaded = ServiceRegistry()
        self.assertIn("test-service", reloaded.services)
        self.assertEqual(reloaded.services["test-service"].path, service.path)

    def test_ordered_services_uses_start_order(self):
        registry = ServiceRegistry()
        registry.services = {
            "HoboStreamer": ServiceDefinition("HoboStreamer", "", "", "", "", "", service_type="HoboStreamer"),
            "hobotools": ServiceDefinition("hobotools", "", "", "", "", "", service_type="hobotools"),
            "other": ServiceDefinition("other", "", "", "", "", "", service_type="other"),
        }
        ordered = registry.ordered_services()
        self.assertEqual([service.name for service in ordered][:2], ["hobotools", "HoboStreamer"])


if __name__ == "__main__":
    unittest.main()
