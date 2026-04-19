#!/usr/bin/env python3
"""Local HTTP control API for OpenVibe Studio.

This module exposes a fetch-friendly JSON API bound to 127.0.0.1 for local
automation, orchestration, and debugging.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

AUTH_TOKEN_ENV = "OPENVIBE_STUDIO_AUTH_TOKEN"
DEFAULT_CONTROL_HOST = "127.0.0.1"
DEFAULT_CONTROL_PORT = 8765


class ControlAPIRequestHandler(BaseHTTPRequestHandler):
    backend = None
    auth_token_env = AUTH_TOKEN_ENV
    control_host = DEFAULT_CONTROL_HOST
    control_port = DEFAULT_CONTROL_PORT

    def do_GET(self) -> None:
        if not self._is_local_request():
            self._send_json({"error": "local-only access allowed"}, status=HTTPStatus.FORBIDDEN)
            return

        path, query = self._parse_path()
        if path == "/health":
            self._send_json({
                "status": "ok",
                "server": "OpenVibe Studio control API",
                "host": self.control_host,
                "port": self.control_port,
                "token_required": bool(os.environ.get(self.auth_token_env)),
            })
            return

        if path == "/control/status":
            self._send_json({"status": "running", "host": self.control_host, "port": self.control_port})
            return

        if path == "/services":
            self._send_json({"services": self._list_services()})
            return

        if path.startswith("/services/"):
            segment = path[len("/services/") :].strip("/")
            self._handle_service_get(segment, query)
            return

        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if not self._is_local_request():
            self._send_json({"error": "local-only access allowed"}, status=HTTPStatus.FORBIDDEN)
            return

        path, _ = self._parse_path()
        if path == "/services/discover":
            if not self._authorize():
                return
            payload = self._read_json()
            result = self._discover_services(payload)
            self._send_json(result)
            return

        if path == "/services/restart_all":
            if not self._authorize():
                return
            self._send_json({"results": self.backend.restart_all_services()})
            return

        if path == "/services/kill_all":
            if not self._authorize():
                return
            self._send_json({"results": self.backend.kill_all_running_processes()})
            return

        if path == "/browser/debug":
            if not self._authorize():
                return
            payload = self._read_json()
            result = self._run_browser_debug(payload)
            self._send_json(result)
            return

        if path.startswith("/services/"):
            if not self._authorize():
                return
            segment = path[len("/services/") :].strip("/")
            payload = self._read_json()
            self._handle_service_post(segment, payload)
            return

        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def _handle_service_get(self, segment: str, query: Dict[str, Any]) -> None:
        parts = segment.split("/")
        service_name = parts[0]
        service = self.backend.services.get(service_name)
        if not service:
            self._send_json({"error": "service not found"}, status=HTTPStatus.NOT_FOUND)
            return

        if len(parts) == 1:
            self._send_json({"service": self._service_data(service)})
            return

        if len(parts) == 2 and parts[1] == "logs":
            lines = int(query.get("lines", [100])[0])
            self._send_json({"service": service_name, "lines": lines, "log": self.backend.read_log(service, lines)})
            return

        if len(parts) == 2 and parts[1] == "health":
            self._send_json({"service": service_name, "health": self.backend.health_status(service)})
            return

        self._send_json({"error": "unknown service endpoint"}, status=HTTPStatus.NOT_FOUND)

    def _handle_service_post(self, segment: str, payload: Dict[str, Any]) -> None:
        parts = segment.split("/")
        service_name = parts[0]
        service = self.backend.services.get(service_name)
        if not service:
            self._send_json({"error": "service not found"}, status=HTTPStatus.NOT_FOUND)
            return

        if len(parts) != 2:
            self._send_json({"error": "invalid service action"}, status=HTTPStatus.BAD_REQUEST)
            return

        action = parts[1]
        if action == "start":
            self._send_json({"service": service_name, "result": self.backend.start_service(service)})
            return
        if action == "stop":
            self._send_json({"service": service_name, "result": self.backend.stop_service(service)})
            return
        if action == "restart":
            self._send_json({"service": service_name, "result": self.backend.restart_service(service)})
            return
        if action == "kill":
            self._send_json({"service": service_name, "result": self.backend.kill_running_processes(service)})
            return
        if action == "wait_healthy":
            timeout = int(payload.get("timeout", 30))
            interval = float(payload.get("interval", 1.0))
            self._send_json({"service": service_name, "result": self.backend.wait_until_healthy(service, timeout, interval)})
            return

        self._send_json({"error": "unsupported service action"}, status=HTTPStatus.BAD_REQUEST)

    def _service_data(self, service: Any) -> Dict[str, Any]:
        data = {
            "name": service.name,
            "path": service.path,
            "command": service.command,
            "env_path": service.env_path,
            "log_path": service.log_path,
            "health_url": service.health_url,
            "service_type": service.service_type,
            "display_name": service.display_name,
            "brand_name": service.brand_name,
            "base_url": service.base_url,
            "status": self.backend.service_status(service),
        }
        return data

    def _list_services(self) -> list[Dict[str, Any]]:
        return [self._service_data(service) for service in self.backend.ordered_services()]

    def _discover_services(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        path_value = payload.get("path")
        if not path_value:
            return {"error": "path is required"}
        candidates = self.backend.discover_services(Path(path_value))
        added = 0
        for service in candidates:
            if service.name in self.backend.services:
                continue
            self.backend.add_service(service)
            added += 1
        return {"discovered": len(candidates), "added": added, "services": [self._service_data(s) for s in candidates]}

    def _run_browser_debug(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        browser_name = payload.get("browser_name") or payload.get("browser")
        target_url = payload.get("target_url") or payload.get("url")
        action = payload.get("action")
        if not browser_name or not target_url or not action:
            return {"error": "browser_name, target_url, and action are required"}
        return self.backend.run_browser_debug(browser_name, target_url, action)

    def _read_json(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length).decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _authorize(self) -> bool:
        token = os.environ.get(self.auth_token_env)
        if not token:
            self._send_json({"error": "authentication token not configured"}, status=HTTPStatus.FORBIDDEN)
            return False

        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and auth_header.split(" ", 1)[1] == token:
            return True

        _, query = self._parse_path()
        query_token = query.get("token", [None])[0] or query.get("auth_token", [None])[0]
        if query_token == token:
            return True

        self._send_json({"error": "invalid auth token"}, status=HTTPStatus.FORBIDDEN)
        return False

    def _is_local_request(self) -> bool:
        peer = self.client_address[0]
        return peer in {"127.0.0.1", "::1", "localhost"}

    def _parse_path(self) -> tuple[str, Dict[str, Any]]:
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        return parsed.path, query

    def _send_json(self, payload: Dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


class LocalControlHTTPServer:
    def __init__(self, backend: Any, host: str = DEFAULT_CONTROL_HOST, port: int = DEFAULT_CONTROL_PORT) -> None:
        self.backend = backend
        self.host = host
        self.port = port
        self.server: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        if self.server is not None:
            return True
        handler_class = self._create_handler()
        try:
            self.server = ThreadingHTTPServer((self.host, self.port), handler_class)
            self.port = self.server.server_address[1]
        except OSError:
            return False

        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return True

    def stop(self) -> None:
        if self.server is None:
            return
        self.server.shutdown()
        self.server.server_close()
        self.server = None
        self.thread = None

    def _create_handler(self) -> type[ControlAPIRequestHandler]:
        backend = self.backend
        auth_token_env = AUTH_TOKEN_ENV
        host = self.host
        port = self.port

        class RequestHandler(ControlAPIRequestHandler):
            pass

        RequestHandler.backend = backend
        RequestHandler.auth_token_env = auth_token_env
        RequestHandler.control_host = host
        RequestHandler.control_port = port
        return RequestHandler

    def is_running(self) -> bool:
        return self.server is not None and self.thread is not None and self.thread.is_alive()

    def url(self) -> str:
        return f"http://{self.host}:{self.port}"
