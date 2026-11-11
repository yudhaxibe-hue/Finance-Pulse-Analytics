import json
import os
import secrets
import sys
from pathlib import Path

APP_NAME = "Finance Pulse Analytics"
APP_SUBTITLE = "Enterprise Financial Performance Intelligence and Profitability Optimization Analytics Platform"
APP_TITLE = f"{APP_NAME}: {APP_SUBTITLE}"
APP_VERSION = "1.1.0"
APP_BUILD = 2

BASE_DIR = Path(__file__).resolve().parent
BUNDLE_DIR = Path(sys._MEIPASS) if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS") else BASE_DIR
TEMPLATE_FOLDER = BUNDLE_DIR / "templates"
STATIC_FOLDER = BUNDLE_DIR / "static"
SAMPLE_FOLDER = BUNDLE_DIR / "data" / "sample_data"


def _load_build_info():
    global APP_VERSION, APP_BUILD
    for candidate in (BUNDLE_DIR / "build_info.json", BASE_DIR / "build_info.json"):
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                if data.get("version"):
                    APP_VERSION = str(data["version"]).strip()
                if data.get("build_number") is not None:
                    APP_BUILD = max(1, int(data["build_number"]))
                break
            except Exception:
                pass


_load_build_info()

GITHUB_REPO = os.environ.get("FINANCE_PULSE_GITHUB_REPO", "yudhaxibe-hue/Finance-Pulse-Analytics").strip()
UPDATE_MANIFEST_URL = os.environ.get(
    "FINANCE_PULSE_MANIFEST_URL",
    f"https://github.com/{GITHUB_REPO}/releases/download/v1.0.0/version.json",
).strip()
DEFAULT_SYNC_URL = os.environ.get("FINANCE_PULSE_SYNC_URL", "").strip()


def default_data_dir():
    override = os.environ.get("FINANCE_PULSE_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "FinancePulseAnalytics"
        if sys.platform.startswith("win"):
            base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
            return Path(base) / "FinancePulseAnalytics"
        return Path.home() / ".local" / "share" / "FinancePulseAnalytics"
    return BASE_DIR


DATA_DIR = default_data_dir()
DATABASE = DATA_DIR / "finance_pulse.db"
UPLOAD_FOLDER = DATA_DIR / "data" / "uploads"
MAX_CONTENT_LENGTH = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {"csv", "xlsx", "json"}


def load_or_create_secret_key(secret_path=None):
    secret_file = Path(secret_path) if secret_path is not None else DATA_DIR / ".flask_secret"
    if secret_file.exists():
        stored = secret_file.read_text(encoding="utf-8").strip()
        if stored:
            return stored
    secret = secrets.token_urlsafe(32)
    try:
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        secret_file.write_text(secret, encoding="utf-8")
    except OSError:
        pass
    return secret


SECRET_KEY = os.environ.get("FINANCE_PULSE_SECRET_KEY") or load_or_create_secret_key()
ADMIN_EMAIL = os.environ.get("FINANCE_PULSE_ADMIN_EMAIL")
ADMIN_PASSWORD = os.environ.get("FINANCE_PULSE_ADMIN_PASSWORD")
