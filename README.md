# OpenVibe Studio

A lightweight Python GUI for managing Hobo local services and OpenVibe projects such as `OpenVibe.Tools`, `OpenVibe.Live`, and `OpenVibe.Games`.

Built with `tkinter` and `ttkbootstrap` for a modern native UI.

## Features

- Select service repository directories and set start commands.
- Edit and save `.env` files for each service.
- Monitor live logs, export logs, copy last `x` lines, and clear logs.
- Start, stop, and restart services from the GUI.
- Health check URL support.
- Local HTTP JSON control API on `127.0.0.1:8765` for external automation.

## Installation

```bash
cd /home/workstation/hobo/OpenVibe.Studio
python3 -m pip install -r requirements.txt
```

## Running

```bash
python3 main.py
```

Or as a package:

```bash
python3 -m openvibe_studio.app
```

## Running tests

```bash
python3 -m unittest discover -s tests
```

## Local HTTP control API

The control API binds to `127.0.0.1:8765` and exposes lightweight JSON endpoints for service orchestration, log inspection, health checks, browser probes, discovery, and stack restart.

Mutating operations require a bearer token set in the environment via `OPENVIBE_STUDIO_AUTH_TOKEN`.

Example usage:

```bash
export OPENVIBE_STUDIO_AUTH_TOKEN=my-local-token
curl http://127.0.0.1:8765/health
curl -H "Authorization: Bearer my-local-token" http://127.0.0.1:8765/services
curl -X POST -H "Authorization: Bearer my-local-token" http://127.0.0.1:8765/services/hobotools/start
curl -X POST http://127.0.0.1:8765/services/hobotools/start?token=my-local-token
curl -X POST -H "Content-Type: application/json" \
  -d '{"browser_name":"chromium","target_url":"http://127.0.0.1:3000","action":"home"}' \
  http://127.0.0.1:8765/browser/debug?token=my-local-token
```

## Notes

- The GUI stores service definitions in `services.json`.
- If a service is already running outside the tool, the manager will detect processes by working directory and command.
- The local control API supports JSON endpoints for service status, lifecycle, logs, health snapshots, discovery, and browser debug.
