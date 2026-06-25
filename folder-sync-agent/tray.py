#!/usr/bin/env python3
"""CityAgent Analytics - Folder Sync system-tray wrapper (optional).

Runs the headless sync observer (from sync_agent.py) in a background
thread and exposes a small system-tray icon with menu items:

    Status        -- log current config + tracked file count
    Pause/Resume  -- stop/start the folder watcher
    Open dashboard-- open the server URL in a browser
    Change folder -- pick a new folder to watch (re-runs setup prompt)
    Quit

This is OPTIONAL. It needs `pystray` and `Pillow`:
    pip install pystray Pillow

If those are missing, it prints a message telling you to use the
headless agent instead:  python sync_agent.py run
"""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser

# Reuse the core agent logic.
import sync_agent as core

try:
    import pystray
    from PIL import Image, ImageDraw
except Exception as exc:  # pragma: no cover - dependency guard
    print(
        "Tray dependencies not available (%s).\n"
        "Install them with: pip install pystray Pillow\n"
        "Or just run the headless agent: python sync_agent.py run" % exc
    )
    sys.exit(1)


class SyncController:
    """Owns the watchdog observer and lets the tray pause/resume it."""

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.state = core.load_state()
        self._observer = None
        self._lock = threading.Lock()
        self.paused = False

    def start(self) -> None:
        with self._lock:
            if self._observer is not None:
                return
            folder = self.cfg.get("folder")
            if not folder or not os.path.isdir(folder):
                core.log.error("Watch folder does not exist: %s", folder)
                return
            try:
                from watchdog.observers import Observer
            except ImportError:
                core.log.error(
                    "'watchdog' not installed. Run: pip install -r requirements.txt"
                )
                return
            # Re-scan on each (re)start to catch changes made while paused.
            core.scan_once(self.cfg, self.state)
            handler = core._make_event_handler(self.cfg, self.state)
            obs = Observer()
            obs.schedule(handler, folder, recursive=True)
            obs.start()
            self._observer = obs
            self.paused = False
            core.log.info("Watching %s", folder)

    def stop(self) -> None:
        with self._lock:
            if self._observer is None:
                return
            self._observer.stop()
            self._observer.join()
            self._observer = None
            self.paused = True
            core.log.info("Paused watcher.")


def _make_icon_image() -> "Image.Image":
    """A simple round-dot icon (no external assets needed)."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, size - 8, size - 8), fill=(43, 108, 176, 255))
    d.ellipse((24, 24, size - 24, size - 24), fill=(255, 255, 255, 255))
    return img


def main() -> int:
    cfg = core.load_config()
    if not cfg:
        print("No config found. Run setup first: python sync_agent.py setup")
        return 1

    controller = SyncController(cfg)
    controller.start()

    def on_status(icon, item):
        state = core.load_state()
        core.log.info(
            "Status: folder=%s tracked=%d paused=%s",
            cfg.get("folder"), len(state), controller.paused,
        )

    def on_toggle(icon, item):
        if controller.paused:
            controller.start()
        else:
            controller.stop()
        icon.update_menu()

    def on_open_dashboard(icon, item):
        url = cfg.get("server_url")
        if url:
            webbrowser.open(url)

    def on_change_folder(icon, item):
        new = input("New folder to watch (absolute path): ").strip()
        if not new:
            return
        new = os.path.abspath(os.path.expanduser(new))
        if not os.path.isdir(new):
            core.log.error("Not a directory: %s", new)
            return
        controller.stop()
        cfg["folder"] = new
        controller.cfg = cfg
        core.save_config(cfg)
        controller.start()

    def on_quit(icon, item):
        controller.stop()
        icon.stop()

    def _paused_text(item):
        return "Resume" if controller.paused else "Pause"

    menu = pystray.Menu(
        pystray.MenuItem("Status", on_status),
        pystray.MenuItem(_paused_text, on_toggle),
        pystray.MenuItem("Open dashboard", on_open_dashboard),
        pystray.MenuItem("Change folder", on_change_folder),
        pystray.MenuItem("Quit", on_quit),
    )

    icon = pystray.Icon(
        "cityagent-sync",
        _make_icon_image(),
        "CityAgent Folder Sync",
        menu,
    )
    icon.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
