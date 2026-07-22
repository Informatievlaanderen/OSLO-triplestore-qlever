"""Logging setup shared across the pipeline."""

import logging
from pathlib import Path


def setup_logger(log_dir: Path) -> None:
    """Configures logging to output to both console and a file in the log directory."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "qlever_initialization.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )