from __future__ import annotations

from pathlib import Path
from typing import List, Tuple


class LogManager:
    def read_log(self, log_path: Path, lines: int = 100) -> str:
        if not log_path.exists():
            return ""
        with log_path.open("r", encoding="utf-8", errors="ignore") as fh:
            return "\n".join(fh.read().splitlines()[-lines:])

    def log_stats(self, log_path: Path) -> Tuple[int, int]:
        if not log_path.exists():
            return 0, 0
        text = log_path.read_text(encoding="utf-8", errors="ignore")
        lines = len(text.splitlines())
        return lines, len(text)

    def clear_log(self, log_path: Path) -> bool:
        try:
            log_path.write_text("", encoding="utf-8")
            return True
        except Exception:
            return False

    def export_log(self, log_path: Path, destination: Path) -> bool:
        try:
            destination.write_bytes(log_path.read_bytes())
            return True
        except Exception:
            return False
