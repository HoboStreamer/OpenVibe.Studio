from __future__ import annotations

import json
import os
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import CONTROL_HOST, CONTROL_PORT, AUTH_TOKEN_ENV, LOCALHOST_ADDRESSES
from ..backend import OpenVibeBackend
from .auth import authorize_request, is_local_request
from .routes import browser, discovery, orchestration, services


class ControlAPIRequestHandler(BaseHTTPRequestHandler):
    backend: Optional[OpenVibeBackend] = None

    def do_GET(self) -> None:
        if not is_local_request(self.client_address[0]):
            self._send_json({"error": "local-only access allowed"}, status=HTTPStatus.FORBIDDEN)
            return

        path, query = self._parse_path()
        if path == "/health":
            self._send_json({
                "status": "ok",
                "server": "OpenVibe Studio control API",
                "host": CONTROL_HOST,
                "port": CONTROL_PORT,
                "token_required": bool(__import__("os").environ.get(AUTH_TOKEN_ENV)),
            })
            return

        if path == "/control/status":
            self._send_json({"status": "running", "host": CONTROL_HOST, "port": CONTROL_PORT})
            return

        if path == "/services":
            self._send_json(services.list_services(self.backend))
            return

        if path.startswith("/services/"):
            segment = path[len("/services/") :].strip("/")
            service_name, action = self._split_segment(segment)
            self._send_json(services.handle_service_get(self.backend, service_name, action, query))
            return

        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if not is_local_request(self.client_address[0]):
            self._send_json({"error": "local-only access allowed"}, status=HTTPStatus.FORBIDDEN)
            return

        path, _ = self._parse_path()
        if path == "/services/discover":
            if not authorize_request(self.path, dict(self.headers)):
                self._send_json({"error": "invalid auth token"}, status=HTTPStatus.FORBIDDEN)
                return
            payload = self._read_json()
            self._send_json(discovery.discover_services(self.backend, payload))
            return

        if path == "/services/restart_all":
            if not authorize_request(self.path, dict(self.headers)):
                self._send_json({"error": "invalid auth token"}, status=HTTPStatus.FORBIDDEN)
                return
            self._send_json(orchestration.restart_all_services(self.backend))
            return

        if path == "/services/kill_all":
            if not authorize_request(self.path, dict(self.headers)):
                self._send_json({"error": "invalid auth token"}, status=HTTPStatus.FORBIDDEN)
                return
            self._send_json(orchestration.kill_all_services(self.backend))
            return

        if path == "/browser/debug":
            if not authorize_request(self.path, dict(self.headers)):
                self._send_json({"error": "invalid auth token"}, status=HTTPStatus.FORBIDDEN)
                return
            payload = self._read_json()
            self._send_json(browser.browser_debug(self.backend, payload))
            return

        if path.startswith("/services/"):
            if not authorize_request(self.path, dict(self.headers)):
                self._send_json({"error": "invalid auth token"}, status=HTTPStatus.FORBIDDEN)
                return
            segment = path[len("/services/") :].strip("/")
            service_name, action = self._split_segment(segment)
            payload = self._read_json()
            self._send_json(services.handle_service_post(self.backend, service_name, action, payload))
            return

        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def _split_segment(self, segment: str) -> tuple[str, str]:
        parts = segment.split("/")
        service_name = parts[0]
        action = parts[1] if len(parts) > 1 else ""
        return service_name, action

    def _read_json(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length).decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

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
    def __init__(self, backend: OpenVibeBackend, host: str = CONTROL_HOST, port: int = CONTROL_PORT) -> None:
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

        class RequestHandler(ControlAPIRequestHandler):
            pass

        RequestHandler.backend = backend
        return RequestHandler

    def is_running(self) -> bool:
        return self.server is not None and self.thread is not None and self.thread.is_alive()

    def url(self) -> str:
        return f"http://{self.host}:{self.port}"
