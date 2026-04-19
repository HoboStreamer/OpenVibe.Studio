#!/usr/bin/env python3
"""OpenVibe Studio GUI for local development and vibe coding.

This tool lets you register repository directories, configure service commands,
inspect and edit .env files, view and export logs, and restart services
via a modern tkinter GUI and a WebSocket control socket.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pyperclip
import psutil
import requests
import ttkbootstrap as tb
import tkinter as tk
import websockets
from dotenv import dotenv_values
from rich import print as rprint
from tkinter import filedialog, messagebox, simpledialog
from ttkbootstrap.widgets.scrolled import ScrolledText

try:
    from playwright.sync_api import Error as PlaywrightError, Page, Playwright, sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:  # pragma: no cover
    Playwright = None  # type: ignore[assignment]
    sync_playwright = None  # type: ignore[assignment]
    PlaywrightError = Exception  # type: ignore[assignment]
    PLAYWRIGHT_AVAILABLE = False

CONFIG_FILE = Path(__file__).parent / "services.json"
CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = 8765
LOG_REFRESH_INTERVAL_MS = 1200
BROWSER_DEBUG_DIR = Path(__file__).parent / "browser-debug"
SERVICE_START_ORDER = ["hobotools", "HoboStreamer", "hobo.quest"]


@dataclass
class ServiceDefinition:
    name: str
    path: str
    command: str
    env_path: str
    log_path: str
    health_url: str
    service_type: str = ""
    display_name: str = ""
    brand_name: str = ""
    base_url: str = ""

    def resolved_path(self) -> Path:
        return Path(self.path).expanduser().resolve()

    def resolved_env_path(self) -> Optional[Path]:
        if self.env_path:
            return Path(self.env_path).expanduser().resolve()
        maybe = self.resolved_path() / ".env"
        return maybe if maybe.exists() else None

    def resolved_log_path(self) -> Path:
        if self.log_path:
            return Path(self.log_path).expanduser().resolve()
        return self.resolved_path() / "service.log"


class OpenVibeBackend:
    def __init__(self) -> None:
        self.services: Dict[str, ServiceDefinition] = {}
        self.processes: Dict[str, psutil.Popen] = {}
        self.load_services()

    def load_services(self) -> None:
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                for item in data.get("services", []):
                    service = ServiceDefinition(**item)
                    self.services[service.name] = service
            except Exception as exc:
                rprint(f"[red]Failed to load services.json: {exc}[/red]")
        else:
            self.save_services()

    def save_services(self) -> None:
        CONFIG_FILE.write_text(
            json.dumps({"services": [asdict(s) for s in self.services.values()]}, indent=2),
            encoding="utf-8",
        )

    def add_service(self, service: ServiceDefinition) -> None:
        self.services[service.name] = service
        self.save_services()

    def remove_service(self, name: str) -> None:
        self.services.pop(name, None)
        self.save_services()

    def _load_env(self, service: ServiceDefinition) -> Dict[str, str]:
        env = os.environ.copy()
        env_path = service.resolved_env_path()
        if env_path and env_path.exists():
            env.update(dotenv_values(env_path))
        return env

    def start_service(self, service: ServiceDefinition) -> str:
        if self.is_service_running(service.name):
            return "already_running"

        cwd = service.resolved_path()
        if not cwd.exists():
            return "path_missing"
        if not service.command.strip():
            return "command_missing"

        env = self._load_env(service)
        log_path = service.resolved_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logfile = open(log_path, "a+", encoding="utf-8")

        popen = psutil.Popen(
            service.command,
            cwd=str(cwd),
            shell=True,
            stdout=logfile,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
        )
        self.processes[service.name] = popen
        return "started"

    def stop_service(self, service: ServiceDefinition) -> str:
        result = "not_running"
        if service.name in self.processes:
            proc = self.processes[service.name]
            if proc.is_running():
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
                try:
                    proc.terminate()
                    proc.wait(timeout=7)
                except (psutil.NoSuchProcess, psutil.TimeoutExpired, PermissionError):
                    try:
                        proc.kill()
                    except Exception:
                        pass
            result = "stopped_found"
        return result

    def restart_service(self, service: ServiceDefinition) -> str:
        self.stop_service(service)
        time.sleep(0.5)
        return self.start_service(service)

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

    def scan_for_lingering_processes(self) -> Dict[str, List[psutil.Process]]:
        matches: Dict[str, List[psutil.Process]] = {}
        for name, service in self.services.items():
            procs = self.find_running_processes(service)
            if procs:
                matches[name] = procs
        return matches

    def kill_running_processes(self, service: ServiceDefinition) -> str:
        found = self.find_running_processes(service)
        if not found:
            return "not_running"
        for proc in found:
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

    def kill_all_running_processes(self) -> Dict[str, str]:
        results: Dict[str, str] = {}
        matches = self.scan_for_lingering_processes()
        for name, service in self.services.items():
            if name in matches:
                results[name] = self.kill_running_processes(service)
            else:
                results[name] = "not_running"
        return results

    def ordered_services(self) -> List[ServiceDefinition]:
        order_map = {key.lower(): index for index, key in enumerate(SERVICE_START_ORDER)}
        return sorted(
            self.services.values(),
            key=lambda service: (
                order_map.get((service.service_type or service.name).lower(), len(order_map)),
                service.name.lower(),
            ),
        )

    def restart_all_services(self) -> Dict[str, str]:
        results: Dict[str, str] = {}
        for service in reversed(self.ordered_services()):
            results[f"stop-{service.name}"] = self.stop_service(service)
            time.sleep(0.2)
        time.sleep(0.5)
        for service in self.ordered_services():
            results[f"start-{service.name}"] = self.start_service(service)
            time.sleep(0.3)
        return results

    def _prepare_browser_debug_dir(self) -> Path:
        BROWSER_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        return BROWSER_DEBUG_DIR

    def browser_test_support(self) -> bool:
        return PLAYWRIGHT_AVAILABLE

    def _make_report_path(self, prefix: str, extension: str) -> Path:
        output_dir = self._prepare_browser_debug_dir()
        timestamp = int(time.time())
        return output_dir / f"{prefix}-{timestamp}.{extension}"

    def _open_browser_type(self, p: Playwright, browser_name: str):
        if browser_name.lower() == "firefox":
            return p.firefox
        return p.chromium

    def run_browser_debug(self, browser_name: str, target_url: str, action: str) -> Dict[str, str]:
        if not PLAYWRIGHT_AVAILABLE:
            return {"status": "missing_playwright", "message": "Install playwright with `pip install playwright` and run `playwright install`."}
        report_path = self._make_report_path(f"browser-{browser_name}-{action}", "txt")
        screenshot_path = self._make_report_path(f"browser-{browser_name}-{action}", "png")
        console_logs: List[str] = []
        request_logs: List[str] = []
        response_logs: List[str] = []
        error_message = ""

        try:
            with sync_playwright() as p:
                browser_type = self._open_browser_type(p, browser_name)
                browser = browser_type.launch(headless=True)
                page = browser.new_page()

                def on_console(msg):
                    console_logs.append(f"{msg.type}: {msg.text}")

                def on_request(request):
                    request_logs.append(f"REQUEST {request.method} {request.url}")

                def on_response(response):
                    response_logs.append(f"RESPONSE {response.status} {response.url}")

                page.on("console", on_console)
                page.on("request", on_request)
                page.on("response", on_response)

                page.goto(target_url, timeout=30000)
                page.wait_for_load_state("networkidle", timeout=15000)
                page.screenshot(path=str(screenshot_path), full_page=True)
                browser.close()
        except PlaywrightError as exc:
            error_message = str(exc)
        except Exception as exc:
            error_message = str(exc)

        report_lines = [
            f"browser={browser_name}",
            f"action={action}",
            f"target_url={target_url}",
            f"screenshot={screenshot_path}",
            f"error={error_message}",
            "", 
            "-- console logs --",
            *console_logs,
            "", 
            "-- request logs --",
            *request_logs,
            "", 
            "-- response logs --",
            *response_logs,
        ]
        report_path.write_text("\n".join(report_lines), encoding="utf-8")
        return {
            "status": "ok" if not error_message else "error",
            "message": error_message or "Browser debug completed",
            "report_path": str(report_path),
            "screenshot_path": str(screenshot_path),
        }

    def is_service_running(self, name: str) -> bool:
        if name in self.processes and self.processes[name].is_running():
            return True
        service = self.services.get(name)
        if not service:
            return False
        return bool(self.find_running_processes(service))

    def service_status(self, service: ServiceDefinition) -> str:
        return "running" if self.is_service_running(service.name) else "stopped"

    def health_status(self, service: ServiceDefinition) -> str:
        if not service.health_url:
            return "no health url"
        try:
            response = requests.get(service.health_url, timeout=3)
            return f"{response.status_code} {response.reason}"
        except Exception as exc:
            return f"error: {exc}"

    def load_env_content(self, service: ServiceDefinition) -> str:
        env_path = service.resolved_env_path()
        if env_path and env_path.exists():
            return env_path.read_text(encoding="utf-8")
        return ""

    def save_env_content(self, service: ServiceDefinition, content: str) -> str:
        env_path = Path(service.env_path or service.resolved_path() / ".env")
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text(content, encoding="utf-8")
        return str(env_path)

    def read_log(self, service: ServiceDefinition, lines: int = 100) -> str:
        log_path = service.resolved_log_path()
        if not log_path.exists():
            return ""
        with log_path.open("r", encoding="utf-8", errors="ignore") as fh:
            data = fh.read().splitlines()
        return "\n".join(data[-lines:])

    def clear_log(self, service: ServiceDefinition) -> bool:
        log_path = service.resolved_log_path()
        try:
            log_path.write_text("", encoding="utf-8")
            return True
        except Exception:
            return False

    def export_log(self, service: ServiceDefinition, destination: str) -> bool:
        log_path = service.resolved_log_path()
        if not log_path.exists():
            return False
        try:
            Path(destination).write_bytes(log_path.read_bytes())
            return True
        except Exception:
            return False

    def parse_service_config(self, service: ServiceDefinition) -> Dict[str, str]:
        env_path = service.resolved_env_path()
        parsed = {
            "base_url": service.base_url,
            "brand_name": service.brand_name,
            "display_name": service.display_name,
            "service_type": service.service_type or service.name,
        }
        if env_path and env_path.exists():
            parsed_env = dotenv_values(env_path)
            parsed["base_url"] = parsed_env.get("BASE_URL") or parsed_env.get("HOBO_TOOLS_URL") or parsed["base_url"]
            parsed["brand_name"] = parsed_env.get("PLATFORM_NAME") or parsed["brand_name"]
            parsed["display_name"] = parsed_env.get("PLATFORM_NAME") or parsed["display_name"]
            parsed["health_url"] = service.health_url
        return parsed

    def discover_services(self, root_path: Path) -> List[ServiceDefinition]:
        root = root_path.expanduser().resolve()
        candidates: List[ServiceDefinition] = []

        def analyze_dir(path: Path) -> Optional[ServiceDefinition]:
            if not path.is_dir():
                return None
            server_config = path / "server" / "config.js"
            env_file = path / ".env"
            service_type = ""
            health_url = ""
            display_name = ""
            brand_name = ""
            base_url = ""
            if not server_config.exists():
                return None
            if path.name in {"hobotools", "hobo-tools"}:
                service_type = "hobotools"
                health_url = "http://127.0.0.1:3100/api/health"
                display_name = "Hobo.Tools"
                brand_name = "Hobo Network"
            elif path.name in {"HoboStreamer.com", "hobostreamer"}:
                service_type = "HoboStreamer"
                health_url = "http://127.0.0.1:3000/api/health"
                display_name = "HoboStreamer"
                brand_name = "Hobo Stream"
            elif path.name in {"hobo-quest", "hobo.quest"}:
                service_type = "hobo.quest"
                health_url = "http://127.0.0.1:3200/api/health"
                display_name = "Hobo Quest"
                brand_name = "Hobo Quest"
            else:
                service_type = path.name
                health_url = ""
                display_name = path.name
                brand_name = path.name
            if env_file.exists():
                parsed = dotenv_values(env_file)
                base_url = parsed.get("BASE_URL") or parsed.get("HOBO_TOOLS_URL") or base_url
                brand_name = parsed.get("PLATFORM_NAME") or parsed.get("platform_name") or brand_name
                display_name = parsed.get("PLATFORM_NAME") or parsed.get("platform_name") or display_name
            return ServiceDefinition(
                name=service_type,
                path=str(path),
                command="npm run dev",
                env_path=str(env_file) if env_file.exists() else "",
                log_path=str(path / "service.log"),
                health_url=health_url,
                service_type=service_type,
                display_name=display_name,
                brand_name=brand_name,
                base_url=base_url,
            )

        dirs = [root] + [d for d in root.iterdir() if d.is_dir()]
        for path in dirs:
            service = analyze_dir(path)
            if service:
                candidates.append(service)
        return candidates


class ControlSocketServer:
    def __init__(self, backend: OpenVibeBackend) -> None:
        self.backend = backend
        self.thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.server: Optional[asyncio.AbstractServer] = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

    def _run_loop(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._serve())
        except Exception as exc:
            rprint(f"[red]Control socket failed: {exc}[/red]")

    async def _serve(self) -> None:
        async with websockets.serve(self._handler, CONTROL_HOST, CONTROL_PORT):
            await asyncio.Future()

    async def _handler(self, websocket, path):
        async for message in websocket:
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                await websocket.send(json.dumps({"error": "invalid json"}))
                continue
            response = await self._process_payload(payload)
            await websocket.send(json.dumps(response))

    async def _process_payload(self, payload: dict) -> dict:
        action = payload.get("action")
        if action == "status":
            return {"status": {name: self.backend.service_status(service) for name, service in self.backend.services.items()}}
        if action in {"start", "stop", "restart"}:
            service_name = payload.get("service")
            service = self.backend.services.get(service_name)
            if not service:
                return {"error": "service not found"}
            if action == "start":
                result = self.backend.start_service(service)
            elif action == "stop":
                result = self.backend.stop_service(service)
            else:
                result = self.backend.restart_service(service)
            return {"result": result}
        if action == "tail":
            service_name = payload.get("service")
            lines = int(payload.get("lines", 100))
            service = self.backend.services.get(service_name)
            if not service:
                return {"error": "service not found"}
            return {"log": self.backend.read_log(service, lines)}
        return {"error": "unknown action"}


class OpenVibeGUI:
    def __init__(self, backend: OpenVibeBackend, control_server: ControlSocketServer) -> None:
        self.backend = backend
        self.control_server = control_server
        self.root = tb.Window("OpenVibe Studio", themename="darkly")
        self.selected_service_name: Optional[str] = None
        self._build_ui()
        self.root.after(LOG_REFRESH_INTERVAL_MS, self._periodic_refresh)

    def _build_ui(self) -> None:
        self.root.geometry("1200x760")
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

        self.service_list = tk.Listbox(self.root, height=18, width=28, selectmode="browse")
        self.service_list.grid(row=0, column=0, padx=12, pady=12, sticky="nsew")
        self.service_list.bind("<<ListboxSelect>>", self._on_service_selected)

        button_row = tb.Frame(self.root)
        button_row.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")
        tb.Button(button_row, text="Add", command=self._on_add).pack(side="left", padx=4)
        tb.Button(button_row, text="Remove", command=self._on_remove).pack(side="left", padx=4)
        tb.Button(button_row, text="Refresh", command=self._refresh_list).pack(side="left", padx=4)
        tb.Button(button_row, text="Discover", command=self._discover_path).pack(side="left", padx=4)
        tb.Button(button_row, text="Kill / Restart", command=self._on_kill_restart_flow).pack(side="left", padx=4)

        notebook = tb.Notebook(self.root)
        notebook.grid(row=0, column=1, rowspan=2, padx=12, pady=12, sticky="nsew")

        self._build_service_tab(notebook)
        self._build_env_tab(notebook)
        self._build_log_tab(notebook)
        self._build_browser_tab(notebook)
        self._refresh_list()

    def _build_service_tab(self, notebook: tb.Notebook) -> None:
        frame = tb.Frame(notebook)
        notebook.add(frame, text="Service")
        for index, label in enumerate(["Name", "Directory", "Start command", "Env file", "Log file", "Health URL"]):
            tb.Label(frame, text=label).grid(row=index, column=0, sticky="w", padx=6, pady=6)

        self.name_var = tb.StringVar()
        self.path_var = tb.StringVar()
        self.command_var = tb.StringVar()
        self.env_path_var = tb.StringVar()
        self.log_path_var = tb.StringVar()
        self.health_url_var = tb.StringVar()
        self.service_type_var = tb.StringVar()
        self.brand_var = tb.StringVar()
        self.base_url_var = tb.StringVar()
        self.status_var = tb.StringVar(value="stopped")

        tb.Entry(frame, textvariable=self.name_var, width=60).grid(row=0, column=1, padx=6, pady=6)
        tb.Entry(frame, textvariable=self.path_var, width=60).grid(row=1, column=1, padx=6, pady=6)
        tb.Button(frame, text="Browse", command=self._browse_path).grid(row=1, column=2, sticky="w", padx=6)
        tb.Entry(frame, textvariable=self.command_var, width=60).grid(row=2, column=1, padx=6, pady=6)
        tb.Entry(frame, textvariable=self.env_path_var, width=60).grid(row=3, column=1, padx=6, pady=6)
        tb.Button(frame, text="Browse", command=self._browse_env).grid(row=3, column=2, sticky="w", padx=6)
        tb.Entry(frame, textvariable=self.log_path_var, width=60).grid(row=4, column=1, padx=6, pady=6)
        tb.Button(frame, text="Browse", command=self._browse_log).grid(row=4, column=2, sticky="w", padx=6)
        tb.Entry(frame, textvariable=self.health_url_var, width=60).grid(row=5, column=1, padx=6, pady=6)
        tb.Label(frame, text="Service Type").grid(row=6, column=0, sticky="w", padx=6, pady=6)
        tb.Entry(frame, textvariable=self.service_type_var, width=60).grid(row=6, column=1, padx=6, pady=6)
        tb.Label(frame, text="Brand Name").grid(row=7, column=0, sticky="w", padx=6, pady=6)
        tb.Entry(frame, textvariable=self.brand_var, width=60).grid(row=7, column=1, padx=6, pady=6)
        tb.Label(frame, text="Base URL").grid(row=8, column=0, sticky="w", padx=6, pady=6)
        tb.Entry(frame, textvariable=self.base_url_var, width=60).grid(row=8, column=1, padx=6, pady=6)

        action_row = tb.Frame(frame)
        action_row.grid(row=9, column=0, columnspan=3, pady=12)
        tb.Button(action_row, text="Save", command=self._on_save).pack(side="left", padx=4)
        tb.Button(action_row, text="Start", command=self._on_start).pack(side="left", padx=4)
        tb.Button(action_row, text="Stop", command=self._on_stop).pack(side="left", padx=4)
        tb.Button(action_row, text="Restart", command=self._on_restart).pack(side="left", padx=4)

        status_frame = tb.Frame(frame)
        status_frame.grid(row=10, column=0, columnspan=3, sticky="w", pady=6)
        tb.Label(status_frame, text="Status:").pack(side="left")
        tb.Label(status_frame, textvariable=self.status_var, bootstyle="warning").pack(side="left", padx=(4, 16))
        tb.Label(status_frame, text="Health:").pack(side="left")
        self.health_text = ScrolledText(frame, width=80, height=5, wrap="word")
        self.health_text.grid(row=11, column=0, columnspan=3, padx=6, pady=6)
        self._set_scrolled_text_state(self.health_text, "disabled")

    def _build_env_tab(self, notebook: tb.Notebook) -> None:
        frame = tb.Frame(notebook)
        notebook.add(frame, text="Env")
        self.env_text = ScrolledText(frame, width=110, height=20)
        self.env_text.grid(row=0, column=0, columnspan=3, padx=12, pady=12)
        tb.Button(frame, text="Load env", command=self._load_env).grid(row=1, column=0, padx=6)
        tb.Button(frame, text="Save env", command=self._save_env).grid(row=1, column=1, padx=6)

    def _build_log_tab(self, notebook: tb.Notebook) -> None:
        frame = tb.Frame(notebook)
        notebook.add(frame, text="Logs")
        self.log_text = ScrolledText(frame, width=110, height=18)
        self.log_text.grid(row=0, column=0, columnspan=6, padx=12, pady=12)
        self.log_lines_var = tb.IntVar(value=100)
        tb.Label(frame, text="Lines:").grid(row=1, column=0, sticky="e")
        tb.Entry(frame, textvariable=self.log_lines_var, width=8).grid(row=1, column=1, sticky="w", padx=4)
        tb.Button(frame, text="Refresh", command=self._refresh_log).grid(row=1, column=2, padx=4)
        tb.Button(frame, text="Copy", command=self._copy_log).grid(row=1, column=3, padx=4)
        tb.Button(frame, text="Export", command=self._export_log).grid(row=1, column=4, padx=4)
        tb.Button(frame, text="Clear", command=self._clear_log).grid(row=1, column=5, padx=4)
        tb.Button(frame, text="Socket start", command=self._start_socket).grid(row=2, column=0, padx=4, pady=8)
        tb.Button(frame, text="Socket stop", command=self._stop_socket).grid(row=2, column=1, padx=4, pady=8)

    def _build_browser_tab(self, notebook: tb.Notebook) -> None:
        frame = tb.Frame(notebook)
        notebook.add(frame, text="Browser")
        tb.Label(frame, text="Browser").grid(row=0, column=0, sticky="w", padx=6, pady=6)
        tb.Label(frame, text="Target URL").grid(row=1, column=0, sticky="w", padx=6, pady=6)

        self.browser_type_var = tb.StringVar(value="chromium")
        self.browser_url_var = tb.StringVar(value="http://127.0.0.1:3000")
        self.browser_status_var = tb.StringVar(value="idle")
        self.browser_report_var = tb.StringVar(value="")

        tb.Combobox(frame, textvariable=self.browser_type_var, values=["chromium", "firefox"], width=20, state="readonly").grid(row=0, column=1, padx=6, pady=6)
        tb.Entry(frame, textvariable=self.browser_url_var, width=72).grid(row=1, column=1, padx=6, pady=6)
        tb.Button(frame, text="Home page", command=lambda: self._run_browser_test("home")).grid(row=2, column=0, padx=6, pady=6)
        tb.Button(frame, text="Live stream probe", command=lambda: self._run_browser_test("live")).grid(row=2, column=1, padx=6, pady=6)
        tb.Button(frame, text="SSO login probe", command=lambda: self._run_browser_test("login")).grid(row=2, column=2, padx=6, pady=6)
        tb.Button(frame, text="Capture screenshot", command=lambda: self._run_browser_test("screenshot")).grid(row=2, column=3, padx=6, pady=6)
        tb.Button(frame, text="Open reports", command=self._open_browser_report_folder).grid(row=2, column=4, padx=6, pady=6)

        tb.Label(frame, text="Status:").grid(row=3, column=0, sticky="w", padx=6, pady=6)
        tb.Entry(frame, textvariable=self.browser_status_var, width=72, state="readonly").grid(row=3, column=1, columnspan=4, padx=6, pady=6)
        tb.Label(frame, text="Latest report:").grid(row=4, column=0, sticky="w", padx=6, pady=6)
        tb.Entry(frame, textvariable=self.browser_report_var, width=72, state="readonly").grid(row=4, column=1, columnspan=4, padx=6, pady=6)

    def _refresh_list(self) -> None:
        self.service_list.delete(0, "end")
        for name in sorted(self.backend.services.keys()):
            self.service_list.insert("end", name)

    def _on_service_selected(self, event=None) -> None:
        selection = self.service_list.curselection()
        if not selection:
            return
        self.selected_service_name = self.service_list.get(selection[0])
        service = self.backend.services[self.selected_service_name]
        self.name_var.set(service.name)
        self.path_var.set(service.path)
        self.command_var.set(service.command)
        self.env_path_var.set(service.env_path)
        self.log_path_var.set(service.log_path)
        self.health_url_var.set(service.health_url)
        self._refresh_service_preview(service)
        self._refresh_health_text(service)
        self.env_text.delete("1.0", "end")
        self.env_text.insert("1.0", self.backend.load_env_content(service))
        self._refresh_log()

    def _discover_path(self) -> None:
        path = filedialog.askdirectory(title="Select root folder to discover services")
        if not path:
            return
        candidates = self.backend.discover_services(Path(path))
        if not candidates:
            messagebox.showinfo("Discover", "No recognizable Hobo services found in that folder.")
            return
        added = 0
        for service in candidates:
            if service.name in self.backend.services:
                continue
            self.backend.add_service(service)
            added += 1
        self._refresh_list()
        messagebox.showinfo("Discover", f"Discovered {len(candidates)} service(s), added {added} new.")

    def _refresh_service_preview(self, service: ServiceDefinition) -> None:
        parsed = self.backend.parse_service_config(service)
        self.service_type_var.set(parsed.get("service_type", service.service_type or service.name))
        self.brand_var.set(parsed.get("brand_name", service.brand_name))
        self.base_url_var.set(parsed.get("base_url", service.base_url))
        self.browser_url_var.set(self._default_browser_url(service))

    def _default_browser_url(self, service: ServiceDefinition) -> str:
        if service.base_url:
            return service.base_url
        if service.health_url:
            return service.health_url.replace("/api/health", "")
        if service.service_type.lower() == "hobostreamer":
            return "http://127.0.0.1:3000"
        if service.service_type.lower() == "hobotools":
            return "http://127.0.0.1:3100"
        if service.service_type.lower() == "hobo.quest":
            return "http://127.0.0.1:3200"
        return "http://127.0.0.1:3000"

    def _run_browser_test(self, action: str) -> None:
        url = self.browser_url_var.get().strip()
        if not url:
            messagebox.showwarning("Browser test", "Enter a target URL first.")
            return
        browser_name = self.browser_type_var.get().strip()
        self.browser_status_var.set(f"running {browser_name}/{action}...")
        thread = threading.Thread(target=self._browser_test_thread, args=(browser_name, url, action), daemon=True)
        thread.start()

    def _set_scrolled_text_state(self, widget: ScrolledText, state: str) -> None:
        if hasattr(widget, "text"):
            widget.text.configure(state=state)
        elif hasattr(widget, "widget"):
            widget.widget.configure(state=state)
        else:
            widget.configure(state=state)

    def _browser_test_thread(self, browser_name: str, url: str, action: str) -> None:
        result = self.backend.run_browser_debug(browser_name, url, action)
        status = result.get("status", "error")
        message = result.get("message", "")
        report_path = result.get("report_path", "")
        self.browser_status_var.set(status)
        self.browser_report_var.set(report_path)
        if status == "error":
            messagebox.showerror("Browser test", f"Browser debug failed: {message}")
        else:
            messagebox.showinfo("Browser test", f"Browser debug completed. Report saved to {report_path}")

    def _open_browser_report_folder(self) -> None:
        folder = self.backend._prepare_browser_debug_dir()
        try:
            if os.name == "nt":
                os.startfile(folder)
            elif os.name == "posix":
                subprocess.Popen(["xdg-open", str(folder)])
            else:
                subprocess.Popen(["open", str(folder)])
        except Exception:
            messagebox.showinfo("Browser reports", f"Report folder: {folder}")

    def _refresh_health_text(self, service: Optional[ServiceDefinition]) -> None:
        self._set_scrolled_text_state(self.health_text, "normal")
        self.health_text.delete("1.0", "end")
        if service is not None:
            health = self.backend.health_status(service)
            self.health_text.insert("1.0", health)
        self._set_scrolled_text_state(self.health_text, "disabled")

    def _browse_path(self) -> None:
        path = filedialog.askdirectory(title="Select service directory")
        if path:
            self.path_var.set(path)

    def _browse_env(self) -> None:
        path = filedialog.askopenfilename(title="Select .env file", filetypes=[("ENV files", "*.env"), ("All files", "*")])
        if path:
            self.env_path_var.set(path)

    def _browse_log(self) -> None:
        path = filedialog.asksaveasfilename(title="Select log file", defaultextension=".log", filetypes=[("Log files", "*.log"), ("All files", "*")])
        if path:
            self.log_path_var.set(path)

    def _on_add(self) -> None:
        name = simpledialog.askstring("Service name", "Enter a service name:")
        if not name:
            return
        if name in self.backend.services:
            messagebox.showwarning("Duplicate service", "A service with that name already exists.")
            return
        service = ServiceDefinition(
            name=name,
            path="",
            command="npm run dev",
            env_path="",
            log_path="",
            health_url="",
            service_type=name,
            display_name=name,
            brand_name=name,
        )
        self.backend.add_service(service)
        self._refresh_list()

    def _on_remove(self) -> None:
        if not self.selected_service_name:
            return
        if messagebox.askyesno("Remove service", f"Remove {self.selected_service_name}?"):
            self.backend.remove_service(self.selected_service_name)
            self.selected_service_name = None
            self._refresh_list()
            self._clear_form()

    def _clear_form(self) -> None:
        self.name_var.set("")
        self.path_var.set("")
        self.command_var.set("")
        self.env_path_var.set("")
        self.log_path_var.set("")
        self.health_url_var.set("")
        self.service_type_var.set("")
        self.brand_var.set("")
        self.base_url_var.set("")
        self.status_var.set("stopped")
        self._refresh_health_text(None)
        self.env_text.delete("1.0", "end")
        self.log_text.delete("1.0", "end")

    def _on_save(self) -> None:
        if not self.selected_service_name:
            messagebox.showwarning("No service", "Select a service first.")
            return
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Invalid name", "Service name may not be empty.")
            return
        service = ServiceDefinition(
            name=name,
            path=self.path_var.get().strip(),
            command=self.command_var.get().strip(),
            env_path=self.env_path_var.get().strip(),
            log_path=self.log_path_var.get().strip(),
            health_url=self.health_url_var.get().strip(),
            service_type=self.service_type_var.get().strip(),
            brand_name=self.brand_var.get().strip(),
            base_url=self.base_url_var.get().strip(),
            display_name=self.name_var.get().strip(),
        )
        if name != self.selected_service_name:
            self.backend.services.pop(self.selected_service_name, None)
            self.selected_service_name = name
        self.backend.services[name] = service
        self.backend.save_services()
        self._refresh_list()
        messagebox.showinfo("Saved", "Service saved successfully.")

    def _service_action(self, action: str) -> None:
        if not self.selected_service_name:
            messagebox.showwarning("No service", "Select a service first.")
            return
        service = self.backend.services[self.selected_service_name]
        thread = threading.Thread(target=self._service_action_thread, args=(action, service), daemon=True)
        thread.start()

    def _service_action_thread(self, action: str, service: ServiceDefinition) -> None:
        if action == "start":
            result = self.backend.start_service(service)
        elif action == "stop":
            result = self.backend.stop_service(service)
        elif action == "restart":
            result = self.backend.restart_service(service)
        else:
            result = "unknown_action"
        rprint(f"[green]{service.name} {action} -> {result}[/green]")
        self.root.after(100, self._refresh_action_state)

    def _on_start(self) -> None:
        self._service_action("start")

    def _on_stop(self) -> None:
        self._service_action("stop")

    def _on_restart(self) -> None:
        self._service_action("restart")

    def _on_kill_restart_flow(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Kill / Restart Stuck Services")
        dialog.geometry("900x520")
        dialog.transient(self.root)
        dialog.grab_set()
        self._show_kill_restart_root(dialog)

    def _show_kill_restart_root(self, dialog: tk.Toplevel) -> None:
        for child in dialog.winfo_children():
            child.destroy()

        intro_frame = tb.Frame(dialog)
        intro_frame.pack(fill="both", expand=True, padx=12, pady=12)

        intro_text = (
            "This tool helps you safely kill or restart Hobo services that may be stuck or lingering. "
            "Choose Kill to identify and terminate only the matching candidate processes. "
            "Choose Restart to find old instances, kill them safely, and then restart the selected configured services."
        )
        tb.Label(intro_frame, text=intro_text, wraplength=820, justify="left").pack(fill="x", pady=(0, 16))

        help_label = tb.Label(intro_frame, text="Use Kill when you only want to remove stray processes. Use Restart when you want to refresh a service from this manager.", bootstyle="info")
        help_label.pack(fill="x", pady=(0, 16))

        action_frame = tb.Frame(intro_frame)
        action_frame.pack(fill="x", pady=(12, 0))
        tb.Button(action_frame, text="Kill candidates", width=18, command=lambda: self._show_kill_selection(dialog)).pack(side="left", padx=8)
        tb.Button(action_frame, text="Restart services", width=18, command=lambda: self._show_restart_selection(dialog)).pack(side="left", padx=8)
        tb.Button(action_frame, text="Cancel", width=10, command=dialog.destroy).pack(side="right", padx=8)

    def _show_kill_selection(self, dialog: tk.Toplevel) -> None:
        for child in dialog.winfo_children():
            child.destroy()

        matches = self.backend.scan_for_lingering_processes()
        main_frame = tb.Frame(dialog)
        main_frame.pack(fill="both", expand=True, padx=12, pady=12)
        if not matches:
            tb.Label(main_frame, text="No running Hobo service processes were found.", bootstyle="success").pack(fill="x", pady=12)
            tb.Button(main_frame, text="Close", command=dialog.destroy).pack(pady=12)
            return

        tb.Label(main_frame, text="Select candidate processes to kill:", font=(None, 12, "bold")).pack(anchor="w", pady=(0, 8))

        self._kill_selection: List[Tuple[str, psutil.Process, tk.BooleanVar]] = []
        scroll_frame = tb.Frame(main_frame)
        scroll_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(scroll_frame, borderwidth=0)
        scrollbar = tb.Scrollbar(scroll_frame, orient="vertical", command=canvas.yview)
        content_frame = tb.Frame(canvas)

        content_frame.bind(
            "<Configure>",
            lambda event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=content_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for service_name, processes in matches.items():
            tb.Label(content_frame, text=f"{service_name} ({len(processes)} process(es))", bootstyle="secondary").pack(anchor="w", pady=(8, 2))
            for proc in processes:
                description = f"pid={proc.pid} name={proc.name()} cwd={proc.cwd() or ''}"
                var = tk.BooleanVar(value=True)
                tb.Checkbutton(content_frame, text=description, variable=var).pack(anchor="w", padx=12)
                self._kill_selection.append((service_name, proc, var))

        action_frame = tb.Frame(dialog)
        action_frame.pack(fill="x", padx=12, pady=(8, 12))
        tb.Button(action_frame, text="Kill selected", command=lambda: self._kill_selected(dialog)).pack(side="left", padx=4)
        tb.Button(action_frame, text="Back", command=lambda: self._show_kill_restart_root(dialog)).pack(side="right", padx=4)
        tb.Button(action_frame, text="Close", command=dialog.destroy).pack(side="right", padx=4)

    def _show_restart_selection(self, dialog: tk.Toplevel) -> None:
        for child in dialog.winfo_children():
            child.destroy()

        main_frame = tb.Frame(dialog)
        main_frame.pack(fill="both", expand=True, padx=12, pady=12)

        tb.Label(main_frame, text="Select configured services to restart:", font=(None, 12, "bold")).pack(anchor="w", pady=(0, 8))
        tb.Label(main_frame, text="The dialog will find old instances for each selected service and restart the service from this manager.").pack(anchor="w", pady=(0, 8))

        self._restart_selection: List[Tuple[str, ServiceDefinition, tk.BooleanVar]] = []
        for service_name, service in self.backend.services.items():
            proc_count = len(self.backend.find_running_processes(service))
            description = f"{service_name} ({service.service_type or service_name}) - {proc_count} current process(es)"
            var = tk.BooleanVar(value=proc_count > 0)
            tb.Checkbutton(main_frame, text=description, variable=var).pack(anchor="w", padx=12, pady=2)
            self._restart_selection.append((service_name, service, var))

        action_frame = tb.Frame(dialog)
        action_frame.pack(fill="x", padx=12, pady=(8, 12))
        tb.Button(action_frame, text="Restart selected", command=lambda: self._restart_selected(dialog)).pack(side="left", padx=4)
        tb.Button(action_frame, text="Back", command=lambda: self._show_kill_restart_root(dialog)).pack(side="right", padx=4)
        tb.Button(action_frame, text="Close", command=dialog.destroy).pack(side="right", padx=4)

    def _kill_selected(self, dialog: tk.Toplevel) -> None:
        selected = [(service, proc) for service, proc, var in self._kill_selection if var.get()]
        if not selected:
            messagebox.showwarning("Kill selected", "No processes were selected.")
            return

        summary_lines: List[str] = []
        for service_name, proc in selected:
            try:
                if proc.is_running():
                    proc.terminate()
                    proc.wait(timeout=7)
                summary_lines.append(f"{service_name}: pid={proc.pid} killed")
            except (psutil.NoSuchProcess, psutil.TimeoutExpired, PermissionError):
                try:
                    proc.kill()
                    summary_lines.append(f"{service_name}: pid={proc.pid} killed by force")
                except Exception as exc:
                    summary_lines.append(f"{service_name}: pid={proc.pid} kill failed ({exc})")

        self._refresh_action_state()
        messagebox.showinfo("Kill selected", "\n".join(summary_lines))
        self._show_kill_selection(dialog)

    def _restart_selected(self, dialog: tk.Toplevel) -> None:
        selected = [(name, service) for name, service, var in self._restart_selection if var.get()]
        if not selected:
            messagebox.showwarning("Restart selected", "No services were selected.")
            return

        summary_lines: List[str] = []
        for service_name, service in selected:
            # Kill any lingering instances safely before restart
            lingering = self.backend.find_running_processes(service)
            if lingering:
                for proc in lingering:
                    try:
                        if proc.is_running():
                            proc.terminate()
                            proc.wait(timeout=7)
                        summary_lines.append(f"{service_name}: stale pid={proc.pid} stopped")
                    except (psutil.NoSuchProcess, psutil.TimeoutExpired, PermissionError):
                        try:
                            proc.kill()
                            summary_lines.append(f"{service_name}: stale pid={proc.pid} killed")
                        except Exception as exc:
                            summary_lines.append(f"{service_name}: stale pid={proc.pid} kill failed ({exc})")
            result = self.backend.restart_service(service)
            summary_lines.append(f"{service_name}: restart {result}")

        self._refresh_action_state()
        messagebox.showinfo("Restart selected", "\n".join(summary_lines))
        self._show_restart_selection(dialog)

    def _on_kill_selected_processes(self, dialog: tk.Toplevel) -> None:
        selected = [(service, proc) for service, proc, var in self._kill_restart_selection if var.get()]
        if not selected:
            messagebox.showwarning("Kill selected", "No processes were selected.")
            return

        summary_lines: List[str] = []
        for service_name, proc in selected:
            try:
                if proc.is_running():
                    proc.terminate()
                    proc.wait(timeout=7)
                summary_lines.append(f"{service_name}: pid={proc.pid} killed")
            except (psutil.NoSuchProcess, psutil.TimeoutExpired, PermissionError):
                try:
                    proc.kill()
                    summary_lines.append(f"{service_name}: pid={proc.pid} killed by force")
                except Exception as exc:
                    summary_lines.append(f"{service_name}: pid={proc.pid} kill failed ({exc})")

        self._refresh_action_state()
        messagebox.showinfo("Kill selected", "\n".join(summary_lines))
        self._show_kill_restart_selection(dialog)

    def _on_restart_selected_services(self, dialog: tk.Toplevel) -> None:
        selected_services = {service for service, proc, var in self._kill_restart_selection if var.get()}
        if not selected_services:
            messagebox.showwarning("Restart selected", "No services were selected.")
            return

        summary_lines: List[str] = []
        for service_name in selected_services:
            service = self.backend.services.get(service_name)
            if not service:
                summary_lines.append(f"{service_name}: service config missing")
                continue
            result = self.backend.restart_service(service)
            summary_lines.append(f"{service_name}: {result}")

        self._refresh_action_state()
        messagebox.showinfo("Restart selected", "\n".join(summary_lines))
        self._show_kill_restart_selection(dialog)

    def _format_process_matches(self, matches: Dict[str, List[psutil.Process]]) -> str:
        lines: List[str] = []
        for name, processes in matches.items():
            lines.append(f"{name}: {len(processes)} process(es)")
            for proc in processes:
                cmd = " ".join(proc.cmdline() or [])
                cwd = proc.cwd() or ""
                lines.append(f"  pid={proc.pid} name={proc.name()} cwd={cwd}")
                if cmd:
                    lines.append(f"    cmd={cmd}")
            lines.append("")
        return "\n".join(lines)

    def _show_text_dialog(self, title: str, content: str) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("900x520")
        text = ScrolledText(dialog, width=110, height=28, wrap="word")
        text.pack(fill="both", expand=True, padx=12, pady=12)
        text.insert("1.0", content)
        self._set_scrolled_text_state(text, "disabled")
        tb.Button(dialog, text="Close", command=dialog.destroy).pack(pady=(0, 12))

    def _load_env(self) -> None:
        if not self.selected_service_name:
            return
        service = self.backend.services[self.selected_service_name]
        self.env_text.delete("1.0", "end")
        self.env_text.insert("1.0", self.backend.load_env_content(service))

    def _save_env(self) -> None:
        if not self.selected_service_name:
            return
        service = self.backend.services[self.selected_service_name]
        destination = self.backend.save_env_content(service, self.env_text.get("1.0", "end"))
        messagebox.showinfo("Saved", f"Env file saved to {destination}")

    def _refresh_log(self) -> None:
        if not self.selected_service_name:
            return
        service = self.backend.services[self.selected_service_name]
        lines = max(1, self.log_lines_var.get())
        content = self.backend.read_log(service, lines)
        self.log_text.delete("1.0", "end")
        self.log_text.insert("1.0", content)

    def _copy_log(self) -> None:
        if not self.selected_service_name:
            return
        service = self.backend.services[self.selected_service_name]
        lines = max(1, self.log_lines_var.get())
        content = self.backend.read_log(service, lines)
        pyperclip.copy(content)
        messagebox.showinfo("Copied", f"Copied last {lines} lines to clipboard")

    def _export_log(self) -> None:
        if not self.selected_service_name:
            return
        destination = filedialog.asksaveasfilename(title="Export log", defaultextension=".log", filetypes=[("Log files", "*.log"), ("All files", "*")])
        if not destination:
            return
        service = self.backend.services[self.selected_service_name]
        ok = self.backend.export_log(service, destination)
        messagebox.showinfo("Export", "Log exported successfully." if ok else "Export failed.")

    def _clear_log(self) -> None:
        if not self.selected_service_name:
            return
        service = self.backend.services[self.selected_service_name]
        if messagebox.askyesno("Clear log", "Truncate the service log file?"):
            ok = self.backend.clear_log(service)
            messagebox.showinfo("Clear log", "Log cleared." if ok else "Clear failed.")
            if ok:
                self.log_text.delete("1.0", "end")

    def _start_socket(self) -> None:
        self.control_server.start()
        messagebox.showinfo("Socket", f"Control socket listening on ws://{CONTROL_HOST}:{CONTROL_PORT}")

    def _stop_socket(self) -> None:
        self.control_server.stop()
        messagebox.showinfo("Socket", "Control socket server stopped.")

    def _refresh_action_state(self) -> None:
        if self.selected_service_name:
            service = self.backend.services[self.selected_service_name]
            self.status_var.set(self.backend.service_status(service))
            self._refresh_health_text(service)
        self._refresh_list()

    def _periodic_refresh(self) -> None:
        if self.selected_service_name:
            service = self.backend.services[self.selected_service_name]
            self.status_var.set(self.backend.service_status(service))
            self._refresh_health_text(service)
        self.root.after(LOG_REFRESH_INTERVAL_MS, self._periodic_refresh)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    backend = OpenVibeBackend()
    control_server = ControlSocketServer(backend)
    gui = OpenVibeGUI(backend, control_server)
    gui.run()

if __name__ == "__main__":
    main()
