from __future__ import annotations

import threading
import tkinter as tk
import ttkbootstrap as tb
from tkinter import ttk
from typing import Any, Callable, Optional

from ...backend import OpenVibeBackend


class ServicesView(tb.Frame):
    def __init__(
        self,
        parent: tk.Widget,
        backend: OpenVibeBackend,
        on_select: Callable[[str], None],
        task_runner: Optional[Any] = None,
    ) -> None:
        super().__init__(parent)
        self.backend = backend
        self.on_select = on_select
        self.task_runner = task_runner
        self._health_cache: dict[str, str] = {}
        self._health_lock = threading.Lock()
        self._refresh_after_id: Optional[str] = None

        style = ttk.Style(self)
        style.configure(
            "Custom.Treeview",
            rowheight=28,
            font=("Segoe UI", 10),
            fieldbackground="#2E3440",
            background="#2E3440",
            foreground="#ECEFF4",
        )
        style.configure(
            "Custom.Treeview.Heading",
            font=("Segoe UI", 10, "bold"),
            background="#4C566A",
            foreground="#ECEFF4",
        )
        style.map(
            "Custom.Treeview",
            background=[("selected", "#81A1C1")],
            foreground=[("selected", "#2E3440")],
        )

        columns = ("name", "status", "health", "lines", "chars")
        self.service_list = ttk.Treeview(
            self,
            columns=columns,
            show="headings",
            height=20,
            style="Custom.Treeview",
        )
        self.service_list.heading("name", text="Service")
        self.service_list.heading("status", text="Status")
        self.service_list.heading("health", text="Health")
        self.service_list.heading("lines", text="Log lines")
        self.service_list.heading("chars", text="Log chars")
        self.service_list.column("name", width=200, anchor="w")
        self.service_list.column("status", width=140, anchor="w")
        self.service_list.column("health", width=140, anchor="w")
        self.service_list.column("lines", width=80, anchor="center")
        self.service_list.column("chars", width=100, anchor="center")
        self.service_list.pack(fill="both", expand=True, padx=8, pady=8)
        self.service_list.bind("<<TreeviewSelect>>", self._on_select)

        self.info_label = tb.Label(self, text="Select a service to see details", wraplength=220, justify="left")
        self.info_label.pack(fill="x", padx=8, pady=(0, 8))
        self.refresh()
        self._schedule_refresh()

    def refresh(self) -> None:
        current_selection = self.service_list.selection()
        selected_id = current_selection[0] if current_selection else None

        for item in self.service_list.get_children():
            self.service_list.delete(item)

        services = self.backend.ordered_services()
        for service in services:
            display_name = service.display_name or service.name
            state = self.backend.service_status(service)
            health = self._health_cache.get(service.name, "checking..." if service.health_url else "no health url")
            lines, chars = self.backend.service_log_stats(service)
            icon = self._status_icon(state, health)
            display_status = f"{icon} {state}"
            self.service_list.insert(
                "",
                "end",
                iid=service.name,
                values=(display_name, display_status, health, str(lines), str(chars)),
            )

        if selected_id and self.service_list.exists(selected_id):
            self.service_list.selection_set(selected_id)

        self.info_label.configure(text=f"{len(services)} service(s) configured")
        if self.task_runner:
            self.task_runner.submit(self._fetch_health_statuses, self._apply_health_statuses)

    def _fetch_health_statuses(self) -> dict[str, str]:
        statuses: dict[str, str] = {}
        for service in self.backend.ordered_services():
            if not service.health_url:
                statuses[service.name] = "no health url"
                continue
            if self.backend.service_status(service) != "running":
                statuses[service.name] = "stopped"
                continue
            statuses[service.name] = self.backend.health_status(service)
        return statuses

    def _apply_health_statuses(self, statuses: dict[str, str]) -> None:
        with self._health_lock:
            for service_name, health in statuses.items():
                previous = self._health_cache.get(service_name)
                if self._is_transient_health_error(health) and previous and not self._is_transient_health_error(previous):
                    continue
                self._health_cache[service_name] = health

        for service_name, health in statuses.items():
            if self.service_list.exists(service_name):
                values = list(self.service_list.item(service_name, "values"))
                status_value = values[1]
                state = status_value.split(" ", 1)[1] if " " in status_value else status_value
                icon = self._status_icon(state, health)
                values[1] = f"{icon} {state}"
                values[2] = health
                self.service_list.item(service_name, values=values)

    def _is_transient_health_error(self, health: str) -> bool:
        return health.startswith("error") or health.startswith("timeout")

    def _status_icon(self, state: str, health: str) -> str:
        if state == "starting":
            return "⏳"
        if state == "running":
            if health.startswith("200"):
                return "✅"
            if health.startswith("error") or health.startswith("timeout"):
                return "⚠️"
            if health == "no health url":
                return "ℹ️"
            return "✔️"
        if state == "stopped":
            return "⛔"
        return "❓"

    def _schedule_refresh(self) -> None:
        self.refresh()
        self._refresh_after_id = self.after(2500, self._schedule_refresh)

    def destroy(self) -> None:
        if self._refresh_after_id is not None:
            self.after_cancel(self._refresh_after_id)
            self._refresh_after_id = None
        super().destroy()

    def _on_select(self, event: tk.Event) -> None:
        selection = self.service_list.selection()
        if not selection:
            return
        service_name = selection[0]
        self.on_select(service_name)
