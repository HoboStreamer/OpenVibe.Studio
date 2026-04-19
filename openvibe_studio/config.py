from __future__ import annotations

from pathlib import Path
from typing import Final

ROOT: Final[Path] = Path(__file__).resolve().parent.parent
CONFIG_FILE: Final[Path] = ROOT / "services.json"
CONTROL_HOST: Final[str] = "127.0.0.1"
CONTROL_PORT: Final[int] = 8765
AUTH_TOKEN_ENV: Final[str] = "OPENVIBE_STUDIO_AUTH_TOKEN"
LOG_REFRESH_INTERVAL_MS: Final[int] = 1200
BROWSER_DEBUG_DIR: Final[Path] = ROOT / "browser-debug"
SUPPORTED_BROWSERS: Final[tuple[str, ...]] = ("chromium", "firefox")
SERVICE_START_ORDER: Final[tuple[str, ...]] = ("hobotools", "HoboStreamer", "hobo.quest")
LOCALHOST_ADDRESSES: Final[tuple[str, ...]] = ("127.0.0.1", "::1", "localhost")
