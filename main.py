#!/usr/bin/env python3
"""OpenVibe Studio entrypoint."""

import logging
import os
import sys
from pathlib import Path

from openvibe_studio.app import run_app

LOG_FILE = Path(__file__).resolve().parent / "openvibe_studio.log"


def configure_logging() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handlers = [logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_FILE, encoding="utf-8")]
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.debug("Starting OpenVibe Studio")
    logging.debug("Environment: %s", dict(os.environ))
    logging.debug("Python: %s", sys.version)
    logging.debug("Working dir: %s", Path.cwd())


def main() -> None:
    configure_logging()
    try:
        run_app()
    except Exception:
        logging.exception("Unhandled exception in OpenVibe Studio")
        raise


if __name__ == "__main__":
    main()
