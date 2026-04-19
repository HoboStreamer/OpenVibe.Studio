#!/usr/bin/env python3
"""Compatibility wrapper for the OpenVibe Studio control API."""

from openvibe_studio.api.server import LocalControlHTTPServer
from openvibe_studio.config import AUTH_TOKEN_ENV, CONTROL_HOST, CONTROL_PORT

__all__ = ["LocalControlHTTPServer", "AUTH_TOKEN_ENV", "CONTROL_HOST", "CONTROL_PORT"]
