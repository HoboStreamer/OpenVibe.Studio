from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as tb
from ttkbootstrap.widgets.scrolled import ScrolledText
from typing import Any, Optional

import pyperclip

from ...backend import OpenVibeBackend


class LogsView:
    def __init__(self, parent: tk.Widget, backend: OpenVibeBackend, task_runner: Any) -> None:
        self.backend = backend
        self.task_runner = task_runner
        self.frame = tb.Frame(parent)
        self.text = ScrolledText(self.frame, width=110, height=20)
        self.text.pack(fill="both", expand=True, padx=12, pady=12)
        controls = tb.Frame(self.frame)
        controls.pack(fill="x", padx=12, pady=(0, 12))
        self.lines_var = tb.IntVar(value=100)
        tb.Label(controls, text="Lines:").pack(side="left")
        tb.Entry(controls, textvariable=self.lines_var, width=8).pack(side="left", padx=4)
        tb.Button(controls, text="Refresh", command=self.refresh).pack(side="left", padx=4)
        tb.Button(controls, text="Copy", command=self.copy).pack(side="left", padx=4)
        tb.Button(controls, text="Clear", command=self.clear).pack(side="left", padx=4)
        self.status = tb.StringVar(value="No service selected")
        tb.Label(controls, textvariable=self.status).pack(side="left", padx=12)
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

        lines = max(1, self.lines_var.get())
        content = self.backend.read_log(service, lines)
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.status.set(f"Showing last {lines} lines for {self.service_name}")

    def copy(self) -> None:
        if not self.service_name:
            return
        content = self.text.get("1.0", "end")
        pyperclip.copy(content)
        self.status.set("Copied log contents to clipboard")

    def clear(self) -> None:
        if not self.service_name:
            return
        service = self.backend.services.get(self.service_name)
        if not service:
            return
        if messagebox.askyesno("Clear log", "Truncate the service log file?"):
            if self.backend.clear_log(service):
                self.text.delete("1.0", "end")
                self.status.set("Log cleared")
            else:
                self.status.set("Clear failed")
