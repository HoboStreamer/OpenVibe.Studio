from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional

import ttkbootstrap as tb
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

from .api.server import LocalControlHTTPServer
from .backend import OpenVibeBackend
from .config import CONTROL_HOST, CONTROL_PORT, LOG_REFRESH_INTERVAL_MS, SUPPORTED_BROWSERS
from .gui.theme import apply_theme
from .gui.views.browser import BrowserView
from .gui.views.diagnostics import DiagnosticsView
from .gui.views.env_editor import EnvEditorView
from .gui.views.logs import LogsView
from .gui.views.services import ServicesView


class TaskRunner:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.pending: list[Callable[[], None]] = []
        self.lock = threading.Lock()
        self.root.after(100, self._poll)

    def submit(self, action: Callable[[], Any], callback: Callable[[Any], None]) -> None:
        future = self.executor.submit(action)

        def _on_done(future_result: Any) -> None:
            try:
                result = future_result.result()
            except Exception as exc:
                result = exc
            with self.lock:
                self.pending.append(lambda: callback(result))

        future.add_done_callback(_on_done)

    def _poll(self) -> None:
        with self.lock:
            items, self.pending = self.pending, []
        for callback in items:
            try:
                callback()
            except Exception:
                pass
        self.root.after(100, self._poll)


class OpenVibeStudioApp:
    def __init__(self) -> None:
        self.backend = OpenVibeBackend()
        self.control_server = LocalControlHTTPServer(self.backend, CONTROL_HOST, CONTROL_PORT)
        self.control_server.start()
        self.root = tb.Window("OpenVibe Studio", themename="darkly")
        apply_theme(self.root)
        self.task_runner = TaskRunner(self.root)
        self.selected_service_name: Optional[str] = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.root.geometry("1240x780")
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

        sidebar = tb.Frame(self.root, bootstyle="secondary")
        sidebar.grid(row=0, column=0, sticky="nswe", padx=12, pady=12)
        sidebar.grid_rowconfigure(1, weight=1)

        tb.Label(sidebar, text="OpenVibe Studio", font=(None, 18, "bold")).grid(row=0, column=0, pady=(8, 16), padx=12)
        self.services_view = ServicesView(sidebar, self.backend, self.on_service_selected, task_runner=self.task_runner)
        self.services_view.grid(row=1, column=0, sticky="nsew", padx=12, pady=4)
        self._build_sidebar_actions(sidebar)

        main_panel = tb.Frame(self.root)
        main_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 12), pady=12)
        self.main_notebook = tb.Notebook(main_panel)
        self.main_notebook.pack(fill="both", expand=True)

        self.env_editor = EnvEditorView(self.main_notebook, self.backend, self.task_runner)
        self.main_notebook.add(self.env_editor.frame, text="Env")

        self.logs_view = LogsView(self.main_notebook, self.backend, self.task_runner)
        self.main_notebook.add(self.logs_view.frame, text="Logs")

        self.browser_view = BrowserView(self.main_notebook, self.backend, self.task_runner)
        self.main_notebook.add(self.browser_view.frame, text="Browser")

        self.diagnostics_view = DiagnosticsView(self.main_notebook, self.backend, self.task_runner)
        self.main_notebook.add(self.diagnostics_view.frame, text="Diagnostics")

        self.status_bar = tk.Frame(self.root, bg=self.root.cget("bg"))
        self.status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.status_label = tb.StringVar(value="Ready")
        tk.Label(self.status_bar, textvariable=self.status_label, anchor="w", bg=self.root.cget("bg")).pack(fill="x", padx=12, pady=6)

    def _build_sidebar_actions(self, sidebar: tb.Frame) -> None:
        action_bar = tb.Frame(sidebar)
        action_bar.grid(row=2, column=0, sticky="ew", padx=12, pady=(8, 12))
        tb.Button(action_bar, text="Refresh", command=self.on_refresh_requested).pack(side="left", padx=2)
        tb.Button(action_bar, text="Discover", command=self.on_discover).pack(side="left", padx=2)
        self.service_action_button = tb.Button(action_bar, text="Start", command=self.on_service_toggle, state="disabled")
        self.service_action_button.pack(side="left", padx=2)
        self.service_reset_button = tb.Button(action_bar, text="Reset DB", command=self.on_reset_db, state="disabled")
        self.service_reset_button.pack(side="left", padx=2)
        self.service_grant_admin_button = tb.Button(action_bar, text="Grant Admin", command=self.on_grant_admin, state="disabled")
        self.service_grant_admin_button.pack(side="left", padx=2)
        tb.Button(action_bar, text="Restart All", command=self.on_restart_all).pack(side="left", padx=2)
        tb.Button(action_bar, text="Kill All", command=self.on_kill_all).pack(side="left", padx=2)

    def _selected_service(self):
        if not self.selected_service_name:
            return None
        return self.backend.services.get(self.selected_service_name)

    def _update_service_action_button(self) -> None:
        service = self._selected_service()
        if service is None:
            self.service_action_button.configure(text="Start", state="disabled")
            self.service_reset_button.configure(state="disabled")
            self.service_grant_admin_button.configure(state="disabled")
            return
        running = self.backend.service_status(service) == "running"
        self.service_action_button.configure(text="Stop" if running else "Start", state="normal")
        self.service_reset_button.configure(state="normal")
        self.service_grant_admin_button.configure(
            state="normal" if service.service_type.lower() in {"hobotools", "hobo-tools"} or service.name.lower() in {"hobotools", "hobo-tools"} else "disabled"
        )

    def on_service_toggle(self) -> None:
        service = self._selected_service()
        if service is None:
            return

        def action() -> str:
            if self.backend.service_status(service) == "running":
                return self.backend.stop_service(service)
            return self.backend.start_service(service)

        def done(result: Any) -> None:
            self.services_view.refresh()
            self._update_service_action_button()
            self.status_label.set(f"{service.name}: {result}")

        self.task_runner.submit(action, done)

    def on_service_selected(self, service_name: str) -> None:
        self.selected_service_name = service_name
        self.env_editor.set_service(service_name)
        self.logs_view.set_service(service_name)
        self.browser_view.set_service(service_name)
        self.diagnostics_view.set_service(service_name)
        self.status_label.set(f"Selected {service_name}")
        self._update_service_action_button()

    def on_reset_db(self) -> None:
        service = self._selected_service()
        if service is None:
            return
        if not messagebox.askyesno(
            "Reset Database",
            f"This will delete the database for {service.display_name or service.name} and reset it to a clean state.\n\n" +
            "You should restart the service after the reset. Continue?",
        ):
            return

        def reset_action() -> str:
            return self.backend.reset_service_database(service)

        def reset_done(result: Any) -> None:
            self.services_view.refresh()
            self._update_service_action_button()
            if isinstance(result, Exception) or str(result).startswith("error:"):
                messagebox.showerror("Reset Database", f"Database reset failed: {result}")
                self.status_label.set(f"{service.name}: reset failed")
            else:
                messagebox.showinfo("Reset Database", f"Database reset completed: {result}")
                self.status_label.set(f"{service.name}: reset completed")

        self.task_runner.submit(reset_action, reset_done)

    def on_grant_admin(self) -> None:
        service = self._selected_service()
        if service is None:
            return
        prompt = simpledialog.askstring("Grant Admin", "Enter username or email to elevate to admin:", parent=self.root)
        if not prompt:
            return
        identifier = prompt.strip()
        by_email = "@" in identifier

        def grant_action() -> str:
            return self.backend.grant_service_admin(service, identifier, by_email)

        def grant_done(result: Any) -> None:
            if isinstance(result, Exception) or str(result).startswith("error:"):
                messagebox.showerror("Grant Admin", f"Grant admin failed: {result}")
                self.status_label.set(f"{service.name}: grant failed")
            else:
                messagebox.showinfo("Grant Admin", f"Admin privileges granted: {result}")
                self.status_label.set(f"{service.name}: granted admin")

        self.task_runner.submit(grant_action, grant_done)

    def on_refresh_requested(self) -> None:
        self.services_view.refresh()
        if self.selected_service_name:
            self.env_editor.refresh()
            self.logs_view.refresh()
            self.browser_view.refresh()
            self.diagnostics_view.refresh()
            self._update_service_action_button()
            self.status_label.set("Refreshed service details")

    def on_discover(self) -> None:
        folder = filedialog.askdirectory(title="Select root folder to discover services")
        if not folder:
            return

        def discover_action() -> dict:
            return self.backend.discover_services(Path(folder))

        def discover_done(result: Any) -> None:
            if isinstance(result, Exception):
                self.status_label.set(f"Discover failed: {result}")
            else:
                self.services_view.refresh()
                self.status_label.set(f"Discovered {result.get('added', 0)} new service(s)")

        self.task_runner.submit(discover_action, discover_done)

    def on_restart_all(self) -> None:
        if not messagebox.askyesno("Restart All", "Restart all configured services?"):
            return

        def restart_action() -> dict:
            return self.backend.restart_all_services()

        def restart_done(result: Any) -> None:
            if isinstance(result, Exception):
                self.status_label.set(f"Restart all failed: {result}")
            else:
                self.status_label.set("Restarted all services")
                self.services_view.refresh()

        self.task_runner.submit(restart_action, restart_done)

    def on_kill_all(self) -> None:
        if not messagebox.askyesno("Kill All", "Kill lingering service processes for all configured services?"):
            return

        def kill_action() -> dict:
            return self.backend.kill_all_running_processes()

        def kill_done(result: Any) -> None:
            if isinstance(result, Exception):
                self.status_label.set(f"Kill all failed: {result}")
            else:
                self.status_label.set("Killed lingering processes")
                self.services_view.refresh()

        self.task_runner.submit(kill_action, kill_done)

    def run(self) -> None:
        self.root.mainloop()


def run_app() -> None:
    OpenVibeStudioApp().run()
