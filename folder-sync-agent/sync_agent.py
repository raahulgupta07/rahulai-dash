#!/usr/bin/env python3
"""CityAgent Analytics - Folder Sync Agent.

A small, standalone, cross-platform desktop agent that watches a local
folder and pushes changed Excel/CSV files to the CityAgent Analytics
server -- similar to how Claude Code syncs a folder.

Usage:
    python sync_agent.py setup     # interactive first-time configuration
    python sync_agent.py agents    # list sync targets (studios/agents)
    python sync_agent.py status    # show config + tracked file count
    python sync_agent.py run       # initial scan + watch (Ctrl-C to stop)
    python sync_agent.py           # defaults to run (runs setup if needed)

Dependencies (pip): requests, watchdog
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional

try:
    import requests
except ImportError:  # pragma: no cover - dependency guard
    requests = None  # type: ignore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIG_DIR = Path.home() / ".cityagent-sync"
CONFIG_PATH = CONFIG_DIR / "config.json"
STATE_PATH = CONFIG_DIR / "state.json"

WATCHED_EXTENSIONS = {".xlsx", ".xlsm", ".xls", ".csv", ".tsv"}

HTTP_TIMEOUT = 30  # seconds
DEBOUNCE_SECONDS = 2.0
CHUNK_SIZE = 1024 * 1024  # 1 MiB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("cityagent-sync")


# ---------------------------------------------------------------------------
# Config / state persistence
# ---------------------------------------------------------------------------

def _ensure_config_dir() -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically: dump to a temp file then os.replace."""
    _ensure_config_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def load_config() -> Optional[dict]:
    if not CONFIG_PATH.exists():
        return None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        log.error("Failed to read config %s: %s", CONFIG_PATH, exc)
        return None


def save_config(cfg: dict) -> None:
    _atomic_write_json(CONFIG_PATH, cfg)
    log.info("Saved config to %s", CONFIG_PATH)


def load_state() -> Dict[str, str]:
    if not STATE_PATH.exists():
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to read state %s: %s (starting fresh)", STATE_PATH, exc)
        return {}


def save_state(state: Dict[str, str]) -> None:
    _atomic_write_json(STATE_PATH, state)


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def sha256_file(path: str) -> str:
    """Compute the SHA-256 of a file's bytes, reading in chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Candidate detection
# ---------------------------------------------------------------------------

def is_candidate(path: str) -> bool:
    """True if path is a watched Excel/CSV file (not a temp/lock file)."""
    name = os.path.basename(path)
    if name.startswith("~$") or name.startswith("."):
        # Office lock files and hidden/temp files.
        return False
    ext = os.path.splitext(name)[1].lower()
    return ext in WATCHED_EXTENSIONS


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

def _require_requests() -> None:
    if requests is None:
        raise RuntimeError(
            "The 'requests' package is not installed. "
            "Run: pip install -r requirements.txt"
        )


def push_file(cfg: dict, path: str, digest: str) -> dict:
    """POST a single file to the server. Returns parsed JSON.

    Multipart form fields:
        file             - the file bytes (filename = basename)
        source_path      - absolute path on this machine
        sha256           - hex digest of the bytes
        machine_label    - this machine's label
        target_studio_id - only sent if configured

    Raises on non-200 / network error (caller handles fail-soft).
    """
    _require_requests()

    server_url = cfg["server_url"].rstrip("/")
    url = f"{server_url}/api/sync/file"
    headers = {"X-API-Key": cfg["api_key"]}

    data = {
        "source_path": os.path.abspath(path),
        "sha256": digest,
        "machine_label": cfg.get("machine_label", socket.gethostname()),
    }
    target = cfg.get("target_studio_id")
    if target:
        data["target_studio_id"] = str(target)

    filename = os.path.basename(path)
    with open(path, "rb") as fh:
        files = {"file": (filename, fh, "application/octet-stream")}
        resp = requests.post(
            url,
            headers=headers,
            data=data,
            files=files,
            timeout=HTTP_TIMEOUT,
        )

    if resp.status_code != 200:
        raise RuntimeError(
            f"Server returned HTTP {resp.status_code}: {resp.text[:300]}"
        )

    try:
        return resp.json()
    except ValueError as exc:
        raise RuntimeError(f"Server returned non-JSON response: {exc}") from exc


def list_agents(cfg: dict) -> list:
    """GET sync targets from the server. Returns a list of dicts."""
    _require_requests()
    server_url = cfg["server_url"].rstrip("/")
    url = f"{server_url}/api/sync/agents"
    headers = {"X-API-Key": cfg["api_key"]}
    resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Server returned HTTP {resp.status_code}: {resp.text[:300]}"
        )
    payload = resp.json()
    # Accept either a bare list or {"agents": [...]} / {"data": [...]}.
    if isinstance(payload, dict):
        for key in ("agents", "data", "studios", "items"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return []
    return payload if isinstance(payload, list) else []


# ---------------------------------------------------------------------------
# Sync logic
# ---------------------------------------------------------------------------

def _log_result(filename: str, status: str) -> None:
    if status == "new":
        log.info("[new agent] %s", filename)
    elif status == "updated":
        log.info("[updated] %s", filename)
    elif status == "skipped":
        log.info("[no change] %s", filename)
    else:
        log.info("[%s] %s", status, filename)


def sync_file(cfg: dict, state: Dict[str, str], path: str) -> str:
    """Sync a single file if its hash changed. Returns a result category:
    'new' | 'updated' | 'skipped' | 'error'.

    Mutates and persists `state`. Fail-soft: never raises.
    """
    abspath = os.path.abspath(path)
    filename = os.path.basename(abspath)

    if not os.path.isfile(abspath):
        return "skipped"

    try:
        digest = sha256_file(abspath)
    except OSError as exc:
        log.error("Could not read %s: %s", abspath, exc)
        return "error"

    if state.get(abspath) == digest:
        # Unchanged from local state -- skip without touching the network.
        log.info("[no change] %s", filename)
        return "skipped"

    try:
        result = push_file(cfg, abspath, digest)
    except Exception as exc:  # fail-soft
        log.error("Push failed for %s: %s", filename, exc)
        return "error"

    status = str(result.get("status", "updated"))
    _log_result(filename, status)

    # Update local state with the new hash on any accepted response.
    state[abspath] = digest
    try:
        save_state(state)
    except OSError as exc:
        log.error("Failed to persist state: %s", exc)

    if status in ("new", "updated", "skipped"):
        return status
    return "updated"


def scan_once(cfg: dict, state: Dict[str, str]) -> Dict[str, int]:
    """Full recursive sweep of the watched folder.

    Returns counts: {new, updated, skipped, error}. Also prunes vanished
    files from local state (deletes are NOT propagated to the server).
    """
    counts = {"new": 0, "updated": 0, "skipped": 0, "error": 0}
    folder = cfg.get("folder")
    if not folder or not os.path.isdir(folder):
        log.error("Watch folder does not exist: %s", folder)
        return counts

    seen = set()
    for root, _dirs, files in os.walk(folder):
        for name in files:
            full = os.path.join(root, name)
            if not is_candidate(full):
                continue
            seen.add(os.path.abspath(full))
            result = sync_file(cfg, state, full)
            counts[result] = counts.get(result, 0) + 1

    # Prune state entries for files that vanished (under this folder only).
    folder_abs = os.path.abspath(folder)
    removed = [
        p for p in list(state.keys())
        if p.startswith(folder_abs + os.sep) and p not in seen
    ]
    if removed:
        for p in removed:
            state.pop(p, None)
            log.info("[gone] dropped from local state: %s", os.path.basename(p))
        try:
            save_state(state)
        except OSError as exc:
            log.error("Failed to persist state after prune: %s", exc)

    return counts


# ---------------------------------------------------------------------------
# Watchdog handler
# ---------------------------------------------------------------------------

def _make_event_handler(cfg: dict, state: Dict[str, str]):
    """Build a watchdog FileSystemEventHandler subclass instance.

    Imported lazily so `setup`/`status`/`agents` work without watchdog.
    """
    from watchdog.events import FileSystemEventHandler

    class _Handler(FileSystemEventHandler):
        def __init__(self) -> None:
            super().__init__()
            self._timers: Dict[str, threading.Timer] = {}
            self._lock = threading.Lock()

        def _schedule(self, path: str) -> None:
            if not is_candidate(path):
                return
            abspath = os.path.abspath(path)
            with self._lock:
                existing = self._timers.pop(abspath, None)
                if existing is not None:
                    existing.cancel()
                timer = threading.Timer(
                    DEBOUNCE_SECONDS, self._fire, args=(abspath,)
                )
                self._timers[abspath] = timer
                timer.daemon = True
                timer.start()

        def _fire(self, abspath: str) -> None:
            with self._lock:
                self._timers.pop(abspath, None)
            try:
                sync_file(cfg, state, abspath)
            except Exception as exc:  # fail-soft, keep watcher alive
                log.error("Handler error for %s: %s", abspath, exc)

        def on_created(self, event):
            if not event.is_directory:
                self._schedule(event.src_path)

        def on_modified(self, event):
            if not event.is_directory:
                self._schedule(event.src_path)

        def on_moved(self, event):
            if not event.is_directory:
                self._schedule(getattr(event, "dest_path", event.src_path))

    return _Handler()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"{label}{suffix}: ").strip()
    except EOFError:
        value = ""
    return value or default


def cmd_setup(_args=None) -> dict:
    """Interactive first-time configuration."""
    print("CityAgent Analytics - Folder Sync setup")
    print("Paste the values from the app's Settings -> Folder Sync page.\n")

    existing = load_config() or {}

    server_url = _prompt(
        "Server URL (e.g. https://analytics.example.com)",
        existing.get("server_url", ""),
    )
    api_key = _prompt(
        "API key (starts with bow_)",
        existing.get("api_key", ""),
    )
    folder = _prompt(
        "Folder to watch (absolute path)",
        existing.get("folder", str(Path.home())),
    )
    machine_label = _prompt(
        "Machine label",
        existing.get("machine_label", socket.gethostname()),
    )
    target_studio_id = _prompt(
        "Target studio/agent id (optional, blank = server default; "
        "run 'agents' to list)",
        existing.get("target_studio_id", ""),
    )

    folder = os.path.abspath(os.path.expanduser(folder))
    if not os.path.isdir(folder):
        log.warning("Folder does not exist yet: %s", folder)

    if api_key and not api_key.startswith("bow_"):
        log.warning("API key does not start with 'bow_' -- double-check it.")

    cfg = {
        "server_url": server_url,
        "api_key": api_key,
        "folder": folder,
        "machine_label": machine_label,
    }
    if target_studio_id:
        cfg["target_studio_id"] = target_studio_id

    save_config(cfg)
    print("\nSetup complete. Start syncing with: python sync_agent.py run")
    return cfg


def cmd_status(_args=None) -> None:
    cfg = load_config()
    if not cfg:
        print("No config found. Run: python sync_agent.py setup")
        return
    state = load_state()
    print("CityAgent Analytics - Folder Sync status")
    print(f"  config file : {CONFIG_PATH}")
    print(f"  state file  : {STATE_PATH}")
    print(f"  server_url  : {cfg.get('server_url')}")
    masked = cfg.get("api_key", "")
    if masked:
        masked = masked[:8] + "..." + masked[-4:] if len(masked) > 12 else "***"
    print(f"  api_key     : {masked}")
    print(f"  folder      : {cfg.get('folder')}")
    print(f"  machine     : {cfg.get('machine_label')}")
    print(f"  target_id   : {cfg.get('target_studio_id', '(server default)')}")
    print(f"  tracked     : {len(state)} file(s)")


def cmd_agents(_args=None) -> None:
    cfg = load_config()
    if not cfg:
        print("No config found. Run: python sync_agent.py setup")
        return
    try:
        agents = list_agents(cfg)
    except Exception as exc:
        log.error("Failed to list agents: %s", exc)
        return
    if not agents:
        print("No sync targets returned by the server.")
        return
    print("Available sync targets (use the id as target_studio_id):")
    print(f"  {'id':<40} name")
    print(f"  {'-' * 40} ----")
    for a in agents:
        if isinstance(a, dict):
            aid = a.get("id") or a.get("studio_id") or a.get("_id") or ""
            name = a.get("name") or a.get("title") or a.get("label") or ""
        else:
            aid, name = str(a), ""
        print(f"  {str(aid):<40} {name}")


def cmd_run(_args=None) -> None:
    cfg = load_config()
    if not cfg:
        print("No config found -- running setup first.\n")
        cfg = cmd_setup()
        if not cfg.get("server_url") or not cfg.get("api_key"):
            log.error("Missing server_url/api_key. Aborting.")
            return

    folder = cfg.get("folder")
    if not folder or not os.path.isdir(folder):
        log.error("Watch folder does not exist: %s", folder)
        return

    if requests is None:
        log.error("'requests' not installed. Run: pip install -r requirements.txt")
        return
    try:
        from watchdog.observers import Observer
    except ImportError:
        log.error("'watchdog' not installed. Run: pip install -r requirements.txt")
        return

    state = load_state()

    log.info("Initial scan of %s ...", folder)
    counts = scan_once(cfg, state)
    log.info(
        "Initial scan done: %d new, %d updated, %d unchanged, %d error",
        counts["new"], counts["updated"], counts["skipped"], counts["error"],
    )

    handler = _make_event_handler(cfg, state)
    observer = Observer()
    observer.schedule(handler, folder, recursive=True)
    observer.start()
    log.info("Watching %s (Ctrl-C to stop)", folder)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Stopping ...")
    finally:
        observer.stop()
        observer.join()
        log.info("Stopped.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sync_agent.py",
        description="CityAgent Analytics - Folder Sync agent.",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("setup", help="interactive configuration")
    sub.add_parser("run", help="initial scan + watch folder")
    sub.add_parser("status", help="show config + tracked file count")
    sub.add_parser("agents", help="list sync targets from the server")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "run"  # default = run

    handlers = {
        "setup": cmd_setup,
        "run": cmd_run,
        "status": cmd_status,
        "agents": cmd_agents,
    }
    handler = handlers.get(command)
    if handler is None:
        build_parser().print_help()
        return 2
    handler(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
