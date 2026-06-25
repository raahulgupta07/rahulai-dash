# CityAgent Analytics - Folder Sync Agent

A small, standalone, cross-platform desktop agent that watches a local folder
and automatically pushes changed **Excel/CSV** files to your CityAgent
Analytics server -- much like Claude Code syncing a folder.

Drop your spreadsheets into the watched folder and they show up in the app.
No manual uploads.

## What it syncs

- File types: `.xlsx`, `.xlsm`, `.xls`, `.csv`, `.tsv` (recursively).
- Office lock/temp files (`~$...`) and hidden dotfiles are ignored.
- **Deletes are ignored.** Removing a local file does **not** delete server
  data -- the file is simply dropped from the local tracking state.

It is change-aware: each file's SHA-256 is cached locally, so unchanged files
are skipped **without any network call**.

## Install

Requires Python 3.8+.

```bash
pip install -r requirements.txt
```

`requests` and `watchdog` are required. `pystray` and `Pillow` are only needed
if you want the optional system-tray icon (`tray.py`).

## Pairing (one-time setup)

In the CityAgent Analytics app, open **Settings -> Folder Sync** and copy the
**Server URL** and the **API key** (it starts with `bow_`). Then run:

```bash
python sync_agent.py setup
```

You'll be prompted for:

- **Server URL** -- e.g. `https://analytics.example.com`
- **API key** -- starts with `bow_`
- **Folder to watch** -- absolute path to the folder containing your files
- **Machine label** -- defaults to your hostname
- **Target studio/agent id** -- optional; leave blank to use the server default

The API key is sent to the server on every request as the **`X-API-Key`**
HTTP header.

## Choosing a target

To see which studios/agents you can sync into (and grab a `target_studio_id`):

```bash
python sync_agent.py agents
```

This calls `GET {server_url}/api/sync/agents` and prints each `id` and `name`.
Re-run `setup` to set the id, or leave it blank for the server default.

## Run

```bash
python sync_agent.py run
```

This does a full initial scan, then watches the folder for create/modify
events (debounced ~2s) until you press **Ctrl-C**. Running with no argument is
the same as `run` (and triggers `setup` first if no config exists).

Each synced file logs one line, e.g.:

```
2026-06-25 10:00:01 INFO [new agent] sales.xlsx
2026-06-25 10:00:02 INFO [updated] q2.xlsx
2026-06-25 10:00:02 INFO [no change] q1.xlsx
```

Network errors are logged and retried on the next event/scan; the watcher
never crashes on a failed upload.

## Other commands

```bash
python sync_agent.py status   # show config (masked key) + tracked file count
```

## Optional: system tray

```bash
python tray.py
```

Shows a tray icon with **Status**, **Pause/Resume**, **Open dashboard**,
**Change folder**, and **Quit**. If `pystray`/`Pillow` aren't installed it
prints a hint and exits -- just use `python sync_agent.py run` instead.

## File locations

- Config: `~/.cityagent-sync/config.json`
- Local state (path -> sha256): `~/.cityagent-sync/state.json`

Both are written atomically (temp file + `os.replace`). No secrets are
hardcoded in the program.

## How it talks to the server

`POST {server_url}/api/sync/file` as `multipart/form-data` with header
`X-API-Key: <api_key>` and these form fields:

| field              | description                                  |
| ------------------ | -------------------------------------------- |
| `file`             | the file bytes (filename = basename)         |
| `source_path`      | absolute path on this machine                |
| `sha256`           | hex SHA-256 of the bytes                      |
| `machine_label`    | this machine's label                         |
| `target_studio_id` | only sent when configured                    |

The server is expected to return HTTP 200 with JSON like
`{"status": "new"|"updated"|"skipped", "data_source_id": ...}`.
