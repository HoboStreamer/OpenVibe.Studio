from __future__ import annotations

import tkinter as tk
import ttkbootstrap as tb
from typing import Any, Optional

from ...config import SUPPORTED_BROWSERS
from ...backend import OpenVibeBackend


class BrowserView:
    def __init__(self, parent: tk.Widget, backend: OpenVibeBackend, task_runner: Any) -> None:
        self.backend = backend
        self.task_runner = task_runner
        self.frame = tb.Frame(parent)
        self.browser_var = tb.StringVar(value=SUPPORTED_BROWSERS[0])
        self.url_var = tb.StringVar(value="http://127.0.0.1:3000")
        self.status = tb.StringVar(value="Idle")

        form = tb.Frame(self.frame)
        form.pack(fill="x", padx=12, pady=12)
        tb.Label(form, text="Browser:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        tb.Combobox(form, textvariable=self.browser_var, values=SUPPORTED_BROWSERS, width=18, state="readonly").grid(row=0, column=1, sticky="w", padx=4, pady=4)
        tb.Label(form, text="URL:").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        tb.Entry(form, textvariable=self.url_var, width=64).grid(row=1, column=1, sticky="w", padx=4, pady=4)

        actions = tb.Frame(self.frame)
        actions.pack(fill="x", padx=12, pady=(0, 12))
        tb.Button(actions, text="Home", command=lambda: self.run_probe("home")).pack(side="left", padx=4)
        tb.Button(actions, text="Live", command=lambda: self.run_probe("live")).pack(side="left", padx=4)
        tb.Button(actions, text="Login", command=lambda: self.run_probe("login")).pack(side="left", padx=4)
        tb.Button(actions, text="Screenshot", command=lambda: self.run_probe("screenshot")).pack(side="left", padx=4)
        tb.Label(actions, textvariable=self.status).pack(side="left", padx=12)

        self.service_name: Optional[str] = None

    def set_service(self, service_name: str) -> None:
        self.service_name = service_name
        self.refresh()

    def refresh(self) -> None:
        service = self.backend.services.get(self.service_name) if self.service_name else None
        if service and service.base_url:
            self.url_var.set(service.base_url)
        self.status.set("Ready")

    def run_probe(self, action: str) -> None:
        def action_fn() -> dict:
            return self.backend.run_browser_debug(self.browser_var.get(), self.url_var.get(), action)

        def on_done(result: Any) -> None:
            if isinstance(result, Exception):
                self.status.set(f"Browser probe failed: {result}")
            else:
                self.status.set(result.get("status", "done"))

        self.status.set(f"Running {action}...")
        self.task_runner.submit(action_fn, on_done)
