import tempfile
import unittest
from pathlib import Path

from openvibe_studio.backend.browser_debug import BrowserDebug, PLAYWRIGHT_AVAILABLE


class BrowserDebugTestCase(unittest.TestCase):
    def test_browser_available_flag(self):
        debug = BrowserDebug(Path(tempfile.gettempdir()))
        self.assertEqual(debug.browser_available(), PLAYWRIGHT_AVAILABLE)

    def test_run_browser_debug_reports_missing_playwright(self):
        debug = BrowserDebug(Path(tempfile.gettempdir()))
        result = debug.run_browser_debug("chromium", "http://127.0.0.1:1", "home")
        if PLAYWRIGHT_AVAILABLE:
            self.assertIn(result["status"], {"ok", "error"})
        else:
            self.assertEqual(result["status"], "missing_playwright")


if __name__ == "__main__":
    unittest.main()
