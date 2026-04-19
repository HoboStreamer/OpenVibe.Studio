import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from openvibe_studio.backend.process_manager import ProcessManager
from openvibe_studio.models.service import ServiceDefinition


class ProcessManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = ProcessManager()
        self.temp_dir = Path(tempfile.mkdtemp())
        self.service = ServiceDefinition(
            name="test-service",
            path=str(self.temp_dir),
            command=f'"{sys.executable}" -c "import time; time.sleep(5)"',
            env_path="",
            log_path=str(self.temp_dir / "service.log"),
            health_url="",
        )

    def tearDown(self) -> None:
        if self.manager.is_service_running(self.service.name):
            self.manager.stop_service(self.service)

    def test_start_and_stop_service(self):
        result = self.manager.start_service(self.service, os.environ.copy())
        self.assertEqual(result, "started")
        self.assertTrue(self.manager.is_service_running(self.service.name))

        stop_result = self.manager.stop_service(self.service)
        self.assertIn(stop_result, {"stopped", "stopped_found"})
        self.assertFalse(self.manager.is_service_running(self.service.name))

    def test_find_running_processes_returns_processes(self):
        self.manager.start_service(self.service, os.environ.copy())
        try:
            procs = self.manager.find_running_processes(self.service)
            self.assertTrue(len(procs) >= 1)
        finally:
            self.manager.stop_service(self.service)

    def test_start_service_reports_missing_command(self):
        broken_service = ServiceDefinition(
            name="broken-service",
            path=str(self.temp_dir),
            command="unlikely-executable-12345 --run",
            env_path="",
            log_path=str(self.temp_dir / "broken.log"),
            health_url="",
        )
        result = self.manager.start_service(broken_service, os.environ.copy())
        self.assertEqual(result, "command_not_found:unlikely-executable-12345")

    def test_resolve_executable_uses_nvm_bin(self):
        fake_nvm_bin = self.temp_dir / "nvm-bin"
        fake_nvm_bin.mkdir()
        npm_path = fake_nvm_bin / "npm"
        npm_path.write_text("")

        resolved = self.manager._resolve_executable("npm", {"PATH": "", "NVM_BIN": str(fake_nvm_bin)})
        self.assertEqual(resolved, str(npm_path))

    def test_start_service_installs_dependencies_when_node_modules_missing(self):
        (self.temp_dir / "package.json").write_text("{}")
        env = os.environ.copy()
        env["PATH"] = ""

        with patch.object(self.manager, "_resolve_executable", return_value="/usr/bin/npm") as resolve_mock:
            with patch.object(self.manager, "_run_command_with_tee", return_value=0) as tee_mock:
                result = self.manager.start_service(self.service, env)

        self.assertEqual(result, "started")
        self.assertTrue(self.manager.is_service_running(self.service.name))
        self.manager.stop_service(self.service)
        self.assertTrue(resolve_mock.called)
        resolve_mock.assert_any_call("npm", unittest.mock.ANY)
        tee_mock.assert_called()


if __name__ == "__main__":
    unittest.main()
