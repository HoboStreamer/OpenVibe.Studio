from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class ServiceDefinition:
    name: str
    path: str
    command: str
    env_path: str
    log_path: str
    health_url: str
    service_type: str = ""
    display_name: str = ""
    brand_name: str = ""
    base_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def resolved_path(self) -> Path:
        return Path(self.path).expanduser().resolve()

    def resolved_env_path(self) -> Optional[Path]:
        if self.env_path:
            return Path(self.env_path).expanduser().resolve()
        maybe = self.resolved_path() / ".env"
        return maybe if maybe.exists() else None

    def resolved_log_path(self) -> Path:
        if self.log_path:
            return Path(self.log_path).expanduser().resolve()
        return self.resolved_path() / "service.log"
