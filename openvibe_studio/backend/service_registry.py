from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from ..config import CONFIG_FILE, SERVICE_START_ORDER
from ..models.service import ServiceDefinition


DEFAULT_SERVICE_TYPES = {
    "hobotools": {
        "health_url": "http://127.0.0.1:3100/api/health",
        "display_name": "Hobo.Tools",
        "brand_name": "Hobo Network",
    },
    "hobo-tools": {
        "health_url": "http://127.0.0.1:3100/api/health",
        "display_name": "Hobo.Tools",
        "brand_name": "Hobo Network",
    },
    "hobostreamer": {
        "health_url": "http://127.0.0.1:3000/api/health",
        "display_name": "HoboStreamer",
        "brand_name": "Hobo Stream",
    },
    "hobostreamer.com": {
        "health_url": "http://127.0.0.1:3000/api/health",
        "display_name": "HoboStreamer",
        "brand_name": "Hobo Stream",
    },
    "hobo.quest": {
        "health_url": "http://127.0.0.1:3200/api/health",
        "display_name": "Hobo Quest",
        "brand_name": "Hobo Quest",
    },
    "hobo-quest": {
        "health_url": "http://127.0.0.1:3200/api/health",
        "display_name": "Hobo Quest",
        "brand_name": "Hobo Quest",
    },
}


class ServiceRegistry:
    def __init__(self) -> None:
        self.services: Dict[str, ServiceDefinition] = {}
        self.load_services()

    def load_services(self) -> None:
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                for item in data.get("services", []):
                    service = ServiceDefinition(**item)
                    self.services[service.name] = service
            except Exception:
                self.services = {}
        else:
            self.save_services()

    def save_services(self) -> None:
        CONFIG_FILE.write_text(
            json.dumps({"services": [service.to_dict() for service in self.services.values()]}, indent=2),
            encoding="utf-8",
        )

    def add_service(self, service: ServiceDefinition) -> None:
        self.services[service.name] = service
        self.save_services()

    def remove_service(self, name: str) -> None:
        self.services.pop(name, None)
        self.save_services()

    def get(self, service_name: str) -> ServiceDefinition | None:
        return self.services.get(service_name)

    def ordered_services(self) -> List[ServiceDefinition]:
        order_map = {key.lower(): index for index, key in enumerate(SERVICE_START_ORDER)}
        return sorted(
            self.services.values(),
            key=lambda service: (
                order_map.get((service.service_type or service.name).lower(), len(order_map)),
                service.name.lower(),
            ),
        )

    def discover_services(self, root_path: Path) -> List[ServiceDefinition]:
        root = root_path.expanduser().resolve()
        candidates: List[ServiceDefinition] = []

        def analyze_dir(path: Path) -> ServiceDefinition | None:
            if not path.is_dir():
                return None
            server_config = path / "server" / "config.js"
            env_file = path / ".env"
            service_type = path.name
            health_url = ""
            display_name = path.name
            brand_name = path.name
            base_url = ""
            if not server_config.exists():
                return None
            defaults = DEFAULT_SERVICE_TYPES.get(path.name.lower())
            if defaults:
                health_url = defaults["health_url"]
                display_name = defaults["display_name"]
                brand_name = defaults["brand_name"]
                service_type = path.name if path.name in DEFAULT_SERVICE_TYPES else path.name
            if env_file.exists():
                from dotenv import dotenv_values

                parsed = dotenv_values(env_file)
                base_url = parsed.get("BASE_URL") or parsed.get("HOBO_TOOLS_URL") or base_url
                brand_name = parsed.get("PLATFORM_NAME") or parsed.get("platform_name") or brand_name
                display_name = parsed.get("PLATFORM_NAME") or parsed.get("platform_name") or display_name
            return ServiceDefinition(
                name=service_type,
                path=str(path),
                command="npm run dev",
                env_path=str(env_file) if env_file.exists() else "",
                log_path=str(path / "service.log"),
                health_url=health_url,
                service_type=service_type,
                display_name=display_name,
                brand_name=brand_name,
                base_url=base_url,
            )

        dirs = [root] + [d for d in root.iterdir() if d.is_dir()]
        for path in dirs:
            service = analyze_dir(path)
            if service:
                candidates.append(service)
        return candidates
