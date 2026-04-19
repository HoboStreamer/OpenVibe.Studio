from __future__ import annotations

import tkinter as tk
import ttkbootstrap as tb
from ttkbootstrap.widgets.scrolled import ScrolledText
from typing import Any, Optional

from ...backend import OpenVibeBackend


class EnvEditorView:
    def __init__(self, parent: tk.Widget, backend: OpenVibeBackend, task_runner: Any) -> None:
        self.backend = backend
        self.task_runner = task_runner
        self.frame = tb.Frame(parent)
        self.text = ScrolledText(self.frame, width=110, height=24)
        self.text.pack(fill="both", expand=True, padx=12, pady=12)
        self.status = tb.StringVar(value="No service selected")
        buttons = tb.Frame(self.frame)
        buttons.pack(fill="x", pady=(0, 12), padx=12)
        tb.Button(buttons, text="Save Env", command=self.save).pack(side="left", padx=4)
        tb.Button(buttons, text="Load Env", command=self.refresh).pack(side="left", padx=4)
        tb.Label(buttons, textvariable=self.status).pack(side="left", padx=12)
        self.service_name: Optional[str] = None

    def set_service(self, service_name: str) -> None:
        self.service_name = service_name
        self.refresh()

    def refresh(self) -> None:
        if not self.service_name:
            self.status.set("No service selected")
            self.text.delete("1.0", "end")
            return

        service = self.backend.services.get(self.service_name)
        if not service:
            self.status.set("Service not found")
            return

        content = self.backend.load_env_content(service)
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.status.set(f"Loaded {self.service_name}")

    def save(self) -> None:
        if not self.service_name:
            self.status.set("No service selected")
            return
        service = self.backend.services.get(self.service_name)
        if not service:
            self.status.set("Service not found")
            return

        content = self.text.get("1.0", "end")
        destination = self.backend.save_env_content(service, content)
        self.status.set(f"Saved env to {destination}")
