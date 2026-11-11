"""Shared pytest fixtures for Finance Pulse Analytics test suites."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest

import app
import config
from database.db import initialize


@pytest.fixture()
def isolated_env(tmp_path):
    """Provide an isolated SQLite DB, uploads, models, backups, and data dirs per test."""
    orig = {
        "DATABASE": config.DATABASE,
        "UPLOAD_FOLDER": config.UPLOAD_FOLDER,
        "MODELS_DIR": config.MODELS_DIR,
        "BACKUPS_DIR": config.BACKUPS_DIR,
        "SAMPLE_FOLDER": config.SAMPLE_FOLDER,
        "DATA_DIR": config.DATA_DIR,
    }
    config.DATA_DIR = tmp_path / "data"
    config.DATABASE = tmp_path / "test_finance.db"
    config.UPLOAD_FOLDER = tmp_path / "uploads"
    config.MODELS_DIR = tmp_path / "models"
    config.BACKUPS_DIR = tmp_path / "backups"
    config.SAMPLE_FOLDER = tmp_path / "sample_data"
    for key in ("DATA_DIR", "UPLOAD_FOLDER", "MODELS_DIR", "BACKUPS_DIR", "SAMPLE_FOLDER"):
        Path(getattr(config, key)).mkdir(parents=True, exist_ok=True)
    initialize()
    app.app.config["TESTING"] = True
    try:
        yield tmp_path
    finally:
        for key, val in orig.items():
            setattr(config, key, val)
