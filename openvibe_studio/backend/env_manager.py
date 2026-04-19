from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

from dotenv import dotenv_values


class EnvManager:
    def load_env(self, env_path: Path) -> Dict[str, str]:
        env = os.environ.copy()
        if env_path and env_path.exists():
            env.update(dotenv_values(env_path))
        return env

    def load_env_content(self, env_path: Path) -> str:
        if env_path and env_path.exists():
            return env_path.read_text(encoding="utf-8")
        return ""

    def save_env_content(self, env_path: Path, content: str) -> None:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text(content, encoding="utf-8")
