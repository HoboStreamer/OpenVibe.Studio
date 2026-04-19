from __future__ import annotations

from typing import Any, Dict, List

from ...models.service import ServiceDefinition


def service_to_dict(backend: Any, service: ServiceDefinition) -> Dict[str, Any]:
    return {
        "name": service.name,
        "path": service.path,
        "command": service.command,
        "env_path": service.env_path,
        "log_path": service.log_path,
        "health_url": service.health_url,
        "service_type": service.service_type,
        "display_name": service.display_name,
        "brand_name": service.brand_name,
        "base_url": service.base_url,
        "status": backend.service_status(service),
    }


def list_services(backend: Any) -> Dict[str, Any]:
    return {"services": [service_to_dict(backend, service) for service in backend.ordered_services()]}


def handle_service_get(backend: Any, service_name: str, action: str, query: Dict[str, Any]) -> Dict[str, Any]:
    service = backend.services.get(service_name)
    if not service:
        return {"error": "service not found"}

    if not action:
        return {"service": service_to_dict(backend, service)}
    if action == "logs":
        lines = int(query.get("lines", [100])[0])
        return {"service": service_name, "lines": lines, "log": backend.read_log(service, lines)}
    if action == "health":
        return {"service": service_name, "health": backend.health_status(service)}
    return {"error": "unknown service endpoint"}


def handle_service_post(backend: Any, service_name: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    service = backend.services.get(service_name)
    if not service:
        return {"error": "service not found"}

    if action == "start":
        return {"service": service_name, "result": backend.start_service(service)}
    if action == "stop":
        return {"service": service_name, "result": backend.stop_service(service)}
    if action == "restart":
        return {"service": service_name, "result": backend.restart_service(service)}
    if action == "kill":
        return {"service": service_name, "result": backend.kill_running_processes(service)}
    if action == "wait_healthy":
        timeout = int(payload.get("timeout", 30))
        interval = float(payload.get("interval", 1.0))
        return {"service": service_name, "result": backend.wait_until_healthy(service, timeout, interval)}
    if action == "reset_db":
        return {"service": service_name, "result": backend.reset_service_database(service)}
    if action == "grant_admin":
        identifier = payload.get("identifier")
        if not identifier:
            return {"service": service_name, "error": "identifier required"}
        by_email = payload.get("by_email", False)
        return {"service": service_name, "result": backend.grant_service_admin(service, identifier, by_email)}
    return {"error": "unsupported service action"}
