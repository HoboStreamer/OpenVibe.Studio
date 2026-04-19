from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import threading
import time
from glob import glob
from pathlib import Path
from typing import Dict, List, Optional

import psutil

from ..models.service import ServiceDefinition

logger = logging.getLogger(__name__)


class ProcessManager:
    def __init__(self) -> None:
        self.processes: Dict[str, psutil.Popen] = {}
        self.starting_services: set[str] = set()
        self._state_lock = threading.Lock()

    def _mark_service_starting(self, service_name: str) -> None:
        with self._state_lock:
            self.starting_services.add(service_name)

    def _unmark_service_starting(self, service_name: str) -> None:
        with self._state_lock:
            self.starting_services.discard(service_name)

    def is_service_starting(self, service_name: str) -> bool:
        with self._state_lock:
            return service_name in self.starting_services

    def service_state(self, service_name: str) -> str:
        if self.is_service_starting(service_name):
            return "starting"
        if self.is_service_running(service_name):
            return "running"
        return "stopped"

    def _which_in_shell(self, executable: str, env: Dict[str, str]) -> Optional[str]:
        if os.name == "nt":
            return None
        for shell in ("bash", "zsh", "fish"):
            try:
                completed = subprocess.run(
                    [shell, "-lc", f"command -v {executable}"],
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=5,
                )
                if completed.returncode == 0:
                    path = completed.stdout.strip()
                    if path:
                        return path
            except Exception:
                continue
        return None

    def _node_tool_directories(self, env: Dict[str, str]) -> List[Path]:
        candidates: List[Path] = []
        nvm_bin = env.get("NVM_BIN")
        if nvm_bin:
            candidates.append(Path(nvm_bin))

        nvm_dir = env.get("NVM_DIR") or str(Path.home() / ".nvm")
        candidates.extend(Path(p).parent for p in glob(str(Path(nvm_dir) / "versions" / "node" / "*" / "bin" / "*")))

        fnm_shims = env.get("FNMSHIMS")
        if fnm_shims:
            candidates.append(Path(fnm_shims))

        candidates.append(Path.home() / ".fnm" / "shims")
        candidates.append(Path.home() / ".local" / "share" / "fnm" / "shims")

        volta_home = env.get("VOLTA_HOME") or str(Path.home() / ".volta")
        candidates.append(Path(volta_home) / "bin")

        candidates.append(Path.home() / ".local" / "bin")
        candidates.append(Path.home() / ".npm-global" / "bin")
        return [candidate for candidate in candidates if candidate.exists()]

    def _normalize_env_for_node_tools(self, env: Dict[str, str]) -> Dict[str, str]:
        normalized = env.copy()
        path_entries = [entry for entry in (normalized.get("PATH", "") or "").split(os.pathsep) if entry]
        for candidate in self._node_tool_directories(env):
            entry = str(candidate)
            if entry not in path_entries:
                path_entries.insert(0, entry)
        normalized["PATH"] = os.pathsep.join(path_entries)
        return normalized

    def _resolve_executable(self, executable: str, env: Dict[str, str]) -> Optional[str]:
        path_str = env["PATH"] if "PATH" in env else os.environ.get("PATH", "")
        path = shutil.which(executable, path=path_str)
        if path:
            return path

        if executable in {"node", "npm", "npx"}:
            normalized_env = self._normalize_env_for_node_tools(env)
            for candidate_dir in self._node_tool_directories(normalized_env):
                candidate = candidate_dir / executable
                if candidate.exists():
                    logger.debug("Resolved %s via node tool directory %s", executable, candidate)
                    return str(candidate)

            shell_path = self._which_in_shell(executable, normalized_env)
            if shell_path:
                logger.debug("Resolved %s via shell lookup %s", executable, shell_path)
                return shell_path

        logger.debug("Failed to resolve executable %s via PATH=%s", executable, path_str)
        return None

    def _run_command_with_tee(self, command: List[str], cwd: Path, env: Dict[str, str], logfile) -> int:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        assert process.stdout is not None
        for line in process.stdout:
            logfile.write(line)
            logfile.flush()
            logger.debug("[%s] %s", cwd, line.rstrip())
        return process.wait()

    def _ensure_dependencies(self, cwd: Path, env: Dict[str, str], logfile) -> Optional[str]:
        package_json = cwd / "package.json"
        node_modules = cwd / "node_modules"
        if not package_json.exists() or node_modules.exists():
            return None

        npm_path = self._resolve_executable("npm", env)
        if not npm_path:
            logger.warning("npm not found for dependency install in %s", cwd)
            return "command_not_found:npm"

        logger.debug("Installing dependencies in %s using %s", cwd, npm_path)
        exitcode = self._run_command_with_tee([npm_path, "install"], cwd, env, logfile)
        if exitcode != 0:
            logger.warning("npm install failed in %s with exit %s", cwd, exitcode)
            return f"install_failed:{exitcode}"
        return None

    def start_service(self, service: ServiceDefinition, env: Dict[str, str]) -> str:
        if self.is_service_running(service.name):
            logger.debug("Service %s already running", service.name)
            return "already_running"

        cwd = service.resolved_path()
        if not cwd.exists():
            logger.warning("Service %s path missing: %s", service.name, cwd)
            return "path_missing"
        if not service.command.strip():
            logger.warning("Service %s has empty command", service.name)
            return "command_missing"

        shell_tokens = shlex.split(service.command, posix=os.name != "nt")
        if shell_tokens:
            first_token = shell_tokens[0]
            if first_token not in {"sh", "bash", "cmd", "powershell", "pwsh"} and not any(
                ch in first_token for ch in ";&|<>*?$()[]{}\"'\\"
            ):
                if self._resolve_executable(first_token, env) is None:
                    logger.warning("Service %s command missing executable: %s", service.name, first_token)
                    return f"command_not_found:{first_token}"

        log_path = service.resolved_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        service_env = self._normalize_env_for_node_tools(env)

        self._mark_service_starting(service.name)
        try:
            with open(log_path, "a+", encoding="utf-8") as logfile:
                install_result = self._ensure_dependencies(cwd, service_env, logfile)
                if install_result is not None:
                    logger.warning("Service %s dependency install result: %s", service.name, install_result)
                    return install_result

                creationflags = 0
                if os.name == "nt":
                    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

                logger.debug("Starting service %s: %s", service.name, service.command)
                popen = psutil.Popen(
                    service.command,
                    cwd=str(cwd),
                    shell=True,
                    stdout=logfile,
                    stderr=subprocess.STDOUT,
                    env=service_env,
                    text=True,
                    creationflags=creationflags,
                )
                self.processes[service.name] = popen
            return "started"
        finally:
            self._unmark_service_starting(service.name)

    def stop_service(self, service: ServiceDefinition) -> str:
        result = "not_running"
        if service.name in self.processes:
            proc = self.processes[service.name]
            if proc.is_running():
                logger.debug("Stopping tracked service process %s pid=%s", service.name, proc.pid)
                proc.terminate()
                try:
                    proc.wait(timeout=7)
                except psutil.TimeoutExpired:
                    proc.kill()
                result = "stopped"
            self.processes.pop(service.name, None)

        found = self.find_running_processes(service)
        if found:
            for proc in found:
                logger.debug("Killing lingering process for %s pid=%s", service.name, proc.pid)
                try:
                    proc.terminate()
                    proc.wait(timeout=7)
                except (psutil.NoSuchProcess, psutil.TimeoutExpired, PermissionError):
                    try:
                        proc.kill()
                    except Exception:
                        pass
            result = "stopped_found"
        if result == "not_running":
            logger.debug("No running process found for service %s", service.name)
        return result

    def restart_service(self, service: ServiceDefinition, env: Dict[str, str]) -> str:
        logger.debug("Restarting service %s", service.name)
        self.stop_service(service)
        time.sleep(0.5)
        return self.start_service(service, env)

    def is_service_running(self, service_name: str) -> bool:
        proc = self.processes.get(service_name)
        if proc and proc.is_running():
            return True
        return False

    def find_running_processes(self, service: ServiceDefinition) -> List[psutil.Process]:
        matches: List[psutil.Process] = []
        target = service.resolved_path()
        for proc in psutil.process_iter(["cwd", "cmdline", "name"]):
            try:
                cwd = proc.info.get("cwd")
                if not cwd:
                    continue
                if Path(cwd).resolve() == target:
                    matches.append(proc)
            except (psutil.NoSuchProcess, PermissionError):
                continue
        return matches

    def scan_for_lingering_processes(self, services: Dict[str, ServiceDefinition]) -> Dict[str, List[psutil.Process]]:
        result: Dict[str, List[psutil.Process]] = {}
        for name, service in services.items():
            procs = self.find_running_processes(service)
            if procs:
                result[name] = procs
        return result

    def kill_running_processes(self, service: ServiceDefinition) -> str:
        found = self.find_running_processes(service)
        if not found:
            logger.debug("No lingering processes to kill for service %s", service.name)
            return "not_running"
        for proc in found:
            logger.debug("Force killing lingering process for %s pid=%s", service.name, proc.pid)
            try:
                proc.terminate()
                proc.wait(timeout=7)
            except (psutil.NoSuchProcess, psutil.TimeoutExpired, PermissionError):
                try:
                    proc.kill()
                except Exception:
                    pass
        self.processes.pop(service.name, None)
        return "killed"

    def kill_all_running_processes(self, services: Dict[str, ServiceDefinition]) -> Dict[str, str]:
        results: Dict[str, str] = {}
        scanning = self.scan_for_lingering_processes(services)
        for name in services:
            if name in scanning:
                results[name] = self.kill_running_processes(services[name])
            else:
                results[name] = "not_running"
        logger.debug("Kill all results: %s", results)
        return results
