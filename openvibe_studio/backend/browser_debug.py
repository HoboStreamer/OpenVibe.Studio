from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List

try:
    from playwright.sync_api import Error as PlaywrightError, Playwright, sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:  # pragma: no cover
    Playwright = None  # type: ignore[assignment]
    sync_playwright = None  # type: ignore[assignment]
    PlaywrightError = Exception  # type: ignore[assignment]
    PLAYWRIGHT_AVAILABLE = False


class BrowserDebug:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def _prepare_browser_debug_dir(self) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir

    def _make_report_path(self, prefix: str, extension: str) -> Path:
        output_dir = self._prepare_browser_debug_dir()
        timestamp = int(time.time())
        return output_dir / f"{prefix}-{timestamp}.{extension}"

    def _open_browser_type(self, p: Playwright, browser_name: str):
        if browser_name.lower() == "firefox":
            return p.firefox
        return p.chromium

    def browser_available(self) -> bool:
        return PLAYWRIGHT_AVAILABLE

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
