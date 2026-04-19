# OpenVibe Studio

A lightweight Python GUI for managing Hobo local services and OpenVibe projects such as `OpenVibe.Tools`, `OpenVibe.Live`, and `OpenVibe.Games`.

Built with `tkinter` and `ttkbootstrap` for a modern native UI.

## Features

- Select service repository directories and set start commands.
- Edit and save `.env` files for each service.
- Monitor live logs, export logs, copy last `x` lines, and clear logs.
- Start, stop, and restart services from the GUI.
- Health check URL support.
- Local WebSocket control server on `127.0.0.1:8765` for external automation.

## Installation

```bash
cd /home/workstation/hobo/service-manager
python3 -m pip install -r requirements.txt
```

## Running

```bash
python3 openvibe_manager.py
```

## Notes

- The GUI stores service definitions in `services.json`.
- If a service is already running outside the tool, the manager will detect processes by working directory and command.
- The local control socket supports JSON commands for status and restart operations.
