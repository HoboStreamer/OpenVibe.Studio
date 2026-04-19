from __future__ import annotations

import os
from typing import Dict
from urllib.parse import urlparse, parse_qs

from ..config import AUTH_TOKEN_ENV, LOCALHOST_ADDRESSES


def authorize_request(path: str, headers: Dict[str, str]) -> bool:
    token = os.environ.get(AUTH_TOKEN_ENV)
    if not token:
        return False

    auth_header = headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") and auth_header.split(" ", 1)[1] == token:
        return True

    parsed = urlparse(path)
    query = parse_qs(parsed.query)
    query_token = query.get("token", [None])[0] or query.get("auth_token", [None])[0]
    return query_token == token


def is_local_request(peer: str) -> bool:
    return peer in LOCALHOST_ADDRESSES
