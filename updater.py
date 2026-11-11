"""In-app update checking, SHA-256 verified desktop downloads, and background wireless sync."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import config

_STATE_LOCK = threading.Lock()
_OUTBOX_LOCK = threading.Lock()
_UPDATE_CACHE: dict[str, Any] = {
    "checked": False,
    "checking": False,
    "update_available": False,
    "local_version": config.APP_VERSION,
    "local_build": config.APP_BUILD,
    "latest_version": config.APP_VERSION,
    "latest_build": config.APP_BUILD,
    "download_url": "",
    "asset_name": "",
    "sha256": "",
    "release_notes": "",
    "release_page_url": f"https://github.com/{config.GITHUB_REPO}/releases/latest",
    "sync_server_url": "",
    "checked_at": "",
    "error": "",
    "download_status": "idle",
    "download_path": "",
    "download_error": "",
}

_SYNC_RUNTIME: dict[str, Any] = {
    "tokens": {},
    "last_sync_at": "",
    "last_sync_ok": None,
    "last_sync_error": "",
}


def normalize_http_url(raw: Optional[str]) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    trimmed = raw.strip()
    if not trimmed:
        return None
    lower = trimmed.lower()
    if lower.startswith(("javascript:", "data:", "vbscript:", "file:")):
        return None
    if "://" not in trimmed:
        trimmed = "https://" + trimmed
    trimmed = trimmed.rstrip("/")
    parsed = urllib.parse.urlparse(trimmed)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        return None
    return trimmed


def parse_semver(version_str: str) -> tuple[int, ...]:
    core = str(version_str or "0").split("+", 1)[0].split("-", 1)[0]
    nums = [int(x) for x in re.findall(r"\d+", core)]
    return tuple(nums or [0])


def is_update_available(
    local_version: str,
    local_build: int,
    remote_version: str,
    remote_build: Optional[int] = None,
) -> bool:
    if remote_build is not None:
        try:
            r_build = int(remote_build)
            l_build = int(local_build or 0)
            if r_build != l_build:
                return r_build > l_build
        except (TypeError, ValueError):
            pass
    return parse_semver(remote_version) > parse_semver(local_version)


def _sync_config_path() -> Path:
    return Path(config.DATA_DIR) / "sync_config.json"


def _sync_outbox_path() -> Path:
    return Path(config.DATA_DIR) / "sync_outbox.json"


def _sync_tokens_path() -> Path:
    return Path(config.DATA_DIR) / "sync_tokens.json"


def _token_cache_key(base_url: str, email: str) -> str:
    return f"{base_url.rstrip('/')}||{email.lower().strip()}"


def _get_sync_token(base_url: str, email: str) -> str:
    norm_email = email.lower().strip()
    if not norm_email:
        return ""
    key = _token_cache_key(base_url, norm_email)
    with _STATE_LOCK:
        cached = _SYNC_RUNTIME["tokens"].get(key) or _SYNC_RUNTIME["tokens"].get(norm_email)
        if cached:
            return cached
    stored = _read_json_file(_sync_tokens_path(), {})
    if isinstance(stored, dict):
        tok = str(stored.get(key) or "")
        if tok:
            with _STATE_LOCK:
                _SYNC_RUNTIME["tokens"][key] = tok
            return tok
    return ""


def _set_sync_token(base_url: str, email: str, token: str) -> None:
    norm_email = email.lower().strip()
    if not norm_email:
        return
    key = _token_cache_key(base_url, norm_email)
    with _STATE_LOCK:
        if token:
            _SYNC_RUNTIME["tokens"][key] = token
        else:
            _SYNC_RUNTIME["tokens"].pop(key, None)
            _SYNC_RUNTIME["tokens"].pop(norm_email, None)
    path = _sync_tokens_path()
    stored = _read_json_file(path, {})
    if not isinstance(stored, dict):
        stored = {}
    if token:
        stored[key] = token
    else:
        stored.pop(key, None)
    _write_json_file(path, stored)
    if os.name == "posix" and path.exists():
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def _read_json_file(path: Path, default: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_json_file(path: Path, payload: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def get_sync_config() -> dict[str, Any]:
    data = _read_json_file(_sync_config_path(), {})
    if not isinstance(data, dict):
        data = {}
    override_url = normalize_http_url(data.get("override_url")) or ""
    manifest_url = normalize_http_url(data.get("manifest_sync_url")) or ""
    env_url = normalize_http_url(os.environ.get("FINANCE_PULSE_SYNC_URL") or config.DEFAULT_SYNC_URL) or ""
    effective_url = override_url or env_url or manifest_url
    outbox = _read_json_file(_sync_outbox_path(), [])
    queue_count = len(outbox) if isinstance(outbox, list) else 0
    with _STATE_LOCK:
        last_at = _SYNC_RUNTIME["last_sync_at"]
        last_ok = _SYNC_RUNTIME["last_sync_ok"]
        last_err = _SYNC_RUNTIME["last_sync_error"]
    return {
        "override_url": override_url,
        "manifest_sync_url": manifest_url,
        "env_sync_url": env_url,
        "effective_url": effective_url,
        "mode": "Manual override" if override_url else ("Environment config" if env_url else ("Automatic manifest" if manifest_url else "Offline local")),
        "queue_count": queue_count,
        "last_sync_at": last_at,
        "last_sync_ok": last_ok,
        "last_sync_error": last_err,
    }


def set_sync_override(raw_url: str) -> tuple[bool, Optional[str]]:
    clean_raw = (raw_url or "").strip()
    data = _read_json_file(_sync_config_path(), {})
    if not isinstance(data, dict):
        data = {}
    if not clean_raw:
        data.pop("override_url", None)
        _write_json_file(_sync_config_path(), data)
        return True, ""
    normalized = normalize_http_url(clean_raw)
    if not normalized:
        return False, None
    data["override_url"] = normalized
    _write_json_file(_sync_config_path(), data)
    return True, normalized


def _platform_asset_from_manifest(manifest: dict[str, Any]) -> tuple[str, str, str, Optional[int], str]:
    key = "windows" if sys.platform.startswith("win") else ("macos" if sys.platform == "darwin" else "linux")
    section = manifest.get(key) or {}
    version = str(section.get("version") or manifest.get("version") or config.APP_VERSION)
    build_raw = section.get("build_number", manifest.get("build_number"))
    build_num = int(build_raw) if build_raw is not None else None
    url = normalize_http_url(section.get("url")) or ""
    sha256 = str(section.get("sha256") or "").strip().lower()
    asset_name = str(section.get("asset_name") or (urllib.parse.urlparse(url).path.rsplit("/", 1)[-1] if url else ""))
    return version, build_num, url, asset_name, sha256


def parse_manifest_dict(manifest: dict[str, Any]) -> dict[str, Any]:
    latest_ver, latest_build, dl_url, asset_name, sha256 = _platform_asset_from_manifest(manifest)
    manifest_sync = normalize_http_url(manifest.get("sync_server_url")) or ""
    avail = is_update_available(config.APP_VERSION, config.APP_BUILD, latest_ver, latest_build)
    return {
        "latest_version": latest_ver,
        "latest_build": latest_build if latest_build is not None else config.APP_BUILD,
        "update_available": avail,
        "download_url": dl_url,
        "asset_name": asset_name,
        "sha256": sha256,
        "release_notes": str(manifest.get("release_notes") or "").strip(),
        "release_page_url": normalize_http_url(manifest.get("release_page_url"))
        or f"https://github.com/{config.GITHUB_REPO}/releases/latest",
        "sync_server_url": manifest_sync,
    }


def check_for_updates(timeout: float = 4.0) -> dict[str, Any]:
    manifest_url = normalize_http_url(config.UPDATE_MANIFEST_URL)
    if not manifest_url:
        with _STATE_LOCK:
            _UPDATE_CACHE["checked"] = True
            _UPDATE_CACHE["checking"] = False
            _UPDATE_CACHE["error"] = "No update manifest URL configured."
            return dict(_UPDATE_CACHE)

    with _STATE_LOCK:
        _UPDATE_CACHE["checking"] = True
        _UPDATE_CACHE["error"] = ""

    try:
        req = urllib.request.Request(
            manifest_url,
            headers={
                "User-Agent": f"FinancePulseAnalytics/{config.APP_VERSION}",
                "Accept": "application/json",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            payload = json.loads(resp.read().decode("utf-8"))
        parsed = parse_manifest_dict(payload)
        cfg_data = _read_json_file(_sync_config_path(), {})
        if isinstance(cfg_data, dict):
            if parsed["sync_server_url"]:
                cfg_data["manifest_sync_url"] = parsed["sync_server_url"]
            else:
                cfg_data.pop("manifest_sync_url", None)
            _write_json_file(_sync_config_path(), cfg_data)
        with _STATE_LOCK:
            _UPDATE_CACHE.update(parsed)
            _UPDATE_CACHE["local_version"] = config.APP_VERSION
            _UPDATE_CACHE["local_build"] = config.APP_BUILD
            _UPDATE_CACHE["checked"] = True
            _UPDATE_CACHE["checking"] = False
            _UPDATE_CACHE["checked_at"] = datetime.utcnow().isoformat() + "Z"
            _UPDATE_CACHE["error"] = ""
    except Exception as exc:
        with _STATE_LOCK:
            _UPDATE_CACHE["local_version"] = config.APP_VERSION
            _UPDATE_CACHE["local_build"] = config.APP_BUILD
            _UPDATE_CACHE["checked"] = True
            _UPDATE_CACHE["checking"] = False
            _UPDATE_CACHE["checked_at"] = datetime.utcnow().isoformat() + "Z"
            _UPDATE_CACHE["error"] = str(exc)

    with _STATE_LOCK:
        return dict(_UPDATE_CACHE)


def start_background_update_check() -> None:
    def _worker():
        check_for_updates(timeout=4.0)
        flush_sync_outbox()

    threading.Thread(target=_worker, name="FinancePulse-Updater", daemon=True).start()


def get_update_status() -> dict[str, Any]:
    with _STATE_LOCK:
        snap = dict(_UPDATE_CACHE)
    snap["local_version"] = config.APP_VERSION
    snap["local_build"] = config.APP_BUILD
    snap["platform"] = sys.platform
    return snap


def _download_dir() -> Path:
    user_dl = Path.home() / "Downloads"
    try:
        user_dl.mkdir(parents=True, exist_ok=True)
        probe = user_dl / ".fp_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return user_dl
    except OSError:
        fallback = Path(config.DATA_DIR) / "updates"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def download_desktop_update() -> dict[str, Any]:
    with _STATE_LOCK:
        dl_url = _UPDATE_CACHE.get("download_url", "")
        expected_sha = _UPDATE_CACHE.get("sha256", "")
        asset_name = _UPDATE_CACHE.get("asset_name", "") or f"FinancePulseAnalytics-{sys.platform}-update.zip"

    # Always refresh version.json before downloading so cached SHAs never lag behind a new release.
    if config.UPDATE_MANIFEST_URL:
        status = check_for_updates(timeout=6.0)
        if not status.get("error") and status.get("download_url"):
            dl_url = status.get("download_url", "")
            expected_sha = status.get("sha256", "")
            asset_name = status.get("asset_name", "") or asset_name

    if not dl_url or not dl_url.startswith("https://"):
        with _STATE_LOCK:
            _UPDATE_CACHE["download_status"] = "error"
            _UPDATE_CACHE["download_error"] = "No verified HTTPS download package is published for this OS yet."
            return dict(_UPDATE_CACHE)

    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", asset_name)
    out_dir = _download_dir()
    dest_path = out_dir / safe_name
    part_path = out_dir / (safe_name + ".part")

    with _STATE_LOCK:
        _UPDATE_CACHE["download_status"] = "downloading"
        _UPDATE_CACHE["download_error"] = ""

    try:
        req = urllib.request.Request(dl_url, headers={"User-Agent": f"FinancePulseAnalytics/{config.APP_VERSION}"})
        hasher = hashlib.sha256()
        with urllib.request.urlopen(req, timeout=45.0) as resp, open(part_path, "wb") as out_f:
            if resp.status != 200:
                raise RuntimeError(f"Download HTTP {resp.status}")
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                hasher.update(chunk)
                out_f.write(chunk)
        digest = hasher.hexdigest().lower()
        if expected_sha and digest != expected_sha.lower():
            part_path.unlink(missing_ok=True)
            raise ValueError(f"SHA-256 verification failed ({digest[:12]} != {expected_sha[:12]})")
        part_path.replace(dest_path)
        with _STATE_LOCK:
            _UPDATE_CACHE["download_status"] = "ready"
            _UPDATE_CACHE["download_path"] = str(dest_path)
            _UPDATE_CACHE["download_error"] = ""
    except Exception as exc:
        part_path.unlink(missing_ok=True)
        with _STATE_LOCK:
            _UPDATE_CACHE["download_status"] = "error"
            _UPDATE_CACHE["download_error"] = str(exc)

    with _STATE_LOCK:
        return dict(_UPDATE_CACHE)


def reveal_downloaded_update() -> tuple[bool, str]:
    with _STATE_LOCK:
        dl_path = _UPDATE_CACHE.get("download_path", "")
    if not dl_path or not Path(dl_path).exists():
        return False, "Update package not downloaded yet."
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", dl_path])
        elif sys.platform.startswith("win"):
            os.startfile(str(Path(dl_path).parent))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(Path(dl_path).parent)])
        return True, dl_path
    except Exception as exc:
        return False, str(exc)


def _is_self_url(base_url: str, server_port: Optional[int]) -> bool:
    if not server_port:
        return False
    parsed = urllib.parse.urlparse(base_url)
    host = (parsed.hostname or "").lower()
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host in {"127.0.0.1", "localhost", "::1"} and port == int(server_port)


def _post_json(url: str, body: dict[str, Any], token: str = "", timeout: float = 4.0) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": f"FinancePulseDesktop/{config.APP_VERSION}",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"error": raw or f"HTTP {err.code}"}
        return err.code, parsed


def mirror_auth_event(action: str, name: str, email: str, password: str, server_port: Optional[int] = None) -> None:
    """Mirror desktop signup/signin to central server asynchronously without keeping plaintext passwords on disk."""
    cfg = get_sync_config()
    base = cfg["effective_url"]
    if not base or _is_self_url(base, server_port):
        return

    def _run():
        endpoint = "/api/v1/auth/register" if action == "register" else "/api/v1/auth/login"
        got_token = False
        try:
            code, payload = _post_json(
                f"{base}{endpoint}",
                {
                    "name": name,
                    "email": email,
                    "password": password,
                    "platform": f"desktop-{sys.platform}",
                    "app_version": config.APP_VERSION,
                },
            )
            if code in (200, 201) and payload.get("token"):
                _set_sync_token(base, email, payload["token"])
                got_token = True
                with _STATE_LOCK:
                    _SYNC_RUNTIME["last_sync_at"] = datetime.utcnow().isoformat() + "Z"
                    _SYNC_RUNTIME["last_sync_ok"] = True
                    _SYNC_RUNTIME["last_sync_error"] = ""
            else:
                with _STATE_LOCK:
                    _SYNC_RUNTIME["last_sync_ok"] = False
                    _SYNC_RUNTIME["last_sync_error"] = payload.get("error") or f"Auth sync HTTP {code}"
        except Exception as exc:
            with _STATE_LOCK:
                _SYNC_RUNTIME["last_sync_ok"] = False
                _SYNC_RUNTIME["last_sync_error"] = str(exc)
        if got_token:
            flush_sync_outbox(server_port=server_port)

    threading.Thread(target=_run, name="FinancePulse-AuthSync", daemon=True).start()


def mirror_dataset_import(
    email: str,
    filename: str,
    client_import_id: str,
    rows: list[dict[str, Any]],
    server_port: Optional[int] = None,
) -> None:
    """Queue and flush imported rows to the central server asynchronously."""
    cfg = get_sync_config()
    base = cfg["effective_url"]
    if not base or _is_self_url(base, server_port):
        return

    norm_email = email.lower().strip()
    token = _get_sync_token(base, norm_email)

    item = {
        "email": norm_email,
        "token": token,
        "filename": filename,
        "client_import_id": client_import_id,
        "rows": rows,
        "queued_at": datetime.utcnow().isoformat() + "Z",
    }
    with _OUTBOX_LOCK:
        queue = _read_json_file(_sync_outbox_path(), [])
        if not isinstance(queue, list):
            queue = []
        if not any(q.get("client_import_id") == client_import_id for q in queue if isinstance(q, dict)):
            queue.append(item)
            _write_json_file(_sync_outbox_path(), queue)

    if token:
        threading.Thread(target=flush_sync_outbox, args=(server_port,), name="FinancePulse-DataSync", daemon=True).start()


def flush_sync_outbox(server_port: Optional[int] = None) -> dict[str, Any]:
    cfg = get_sync_config()
    base = cfg["effective_url"]
    if not base or _is_self_url(base, server_port):
        return get_sync_config()

    with _OUTBOX_LOCK:
        queue = _read_json_file(_sync_outbox_path(), [])
        if not isinstance(queue, list) or not queue:
            return get_sync_config()

        remaining = []
        last_err = ""
        any_ok = False
        for idx, entry in enumerate(queue):
            if not isinstance(entry, dict):
                continue
            entry_email = str(entry.get("email", "")).lower().strip()
            token = _get_sync_token(base, entry_email) or entry.get("token") or ""
            if not token:
                last_err = "Sign in while online to link offline account sync."
                remaining.append(entry)
                continue
            try:
                code, payload = _post_json(
                    f"{base}/api/v1/sync/import",
                    {
                        "filename": entry.get("filename", "dataset.csv"),
                        "client_import_id": entry.get("client_import_id", ""),
                        "platform": f"desktop-{sys.platform}",
                        "rows": entry.get("rows", []),
                    },
                    token=token,
                    timeout=8.0,
                )
                if code in (200, 201):
                    any_ok = True
                elif code == 401:
                    last_err = "Session token expired on central server."
                    _set_sync_token(base, entry_email, "")
                    updated_entry = dict(entry)
                    updated_entry["token"] = ""
                    remaining.append(updated_entry)
                else:
                    last_err = payload.get("error") or f"Sync HTTP {code}"
                    remaining.extend(queue[idx:])
                    break
            except Exception as exc:
                last_err = str(exc)
                remaining.extend(queue[idx:])
                break

        _write_json_file(_sync_outbox_path(), remaining)
    with _STATE_LOCK:
        if any_ok or last_err:
            _SYNC_RUNTIME["last_sync_at"] = datetime.utcnow().isoformat() + "Z"
            _SYNC_RUNTIME["last_sync_ok"] = bool(any_ok and not last_err)
            _SYNC_RUNTIME["last_sync_error"] = last_err
    return get_sync_config()
