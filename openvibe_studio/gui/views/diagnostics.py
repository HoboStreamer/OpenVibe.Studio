from __future__ import annotations

import tkinter as tk
import ttkbootstrap as tb
from ttkbootstrap.widgets.scrolled import ScrolledText
from typing import Any, Optional

from ...backend import OpenVibeBackend


class DiagnosticsView:
    def __init__(self, parent: tk.Widget, backend: OpenVibeBackend, task_runner: Any) -> None:
        self.backend = backend
        self.task_runner = task_runner
        self.frame = tb.Frame(parent)
        self.text = ScrolledText(self.frame, width=110, height=20, wrap="word")
        self.text.pack(fill="both", expand=True, padx=12, pady=12)
        controls = tb.Frame(self.frame)
        controls.pack(fill="x", padx=12, pady=(0, 12))
        tb.Button(controls, text="Refresh Diagnostics", command=self.refresh).pack(side="left", padx=4)
        self.status = tb.StringVar(value="No diagnostics yet")
        tb.Label(controls, textvariable=self.status).pack(side="left", padx=12)
        self.service_name: Optional[str] = None

    def set_service(self, service_name: str) -> None:
        self.service_name = service_name
        self.refresh()

    def refresh(self) -> None:
        def action() -> dict:
            results = {}
            if self.service_name:
                service = self.backend.services.get(self.service_name)
                if service:
                    results["service_status"] = self.backend.service_status(service)
                    results["health"] = self.backend.health_status(service)
            results["lingering_processes"] = self.backend.scan_for_lingering_processes()
            return results

        def on_done(result: Any) -> None:
            if isinstance(result, Exception):
                self.status.set(f"Diagnostics failed: {result}")
                return
            self.text.delete("1.0", "end")
            if self.service_name:
                self.text.insert("1.0", f"Service: {self.service_name}\n")
                self.text.insert("end", f"Status: {result.get('service_status')}\n")
                self.text.insert("end", f"Health: {result.get('health')}\n\n")
            self.text.insert("end", "Lingering processes:\n")
            for name, procs in result.get("lingering_processes", {}).items():
                self.text.insert("end", f"- {name}: {len(procs)} process(es)\n")
                for proc in procs:
                    try:
                        cwd = proc.cwd() or ""
                    except Exception:
                        cwd = ""
                    try:
                        cmdline = " ".join(proc.cmdline())
                    except Exception:
                        cmdline = proc.name() if hasattr(proc, "name") else ""
                    display_cmd = cmdline if cmdline else proc.name() if hasattr(proc, "name") else ""
                    self.text.insert(
                        "end",
                        f"    pid={proc.pid} cwd={cwd} cmd={display_cmd}\n",
                    )
            self.status.set("Diagnostics updated")

        self.task_runner.submit(action, on_done)
