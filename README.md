# Web Runner (Flask MVP)

A **minimal, stable MVP**: a Flask web app on Linux for **long-running video processing**. You upload a video in the browser; the server runs a **bash pipeline** (`whole.sh`) in a **background thread**, streams **stdout/stderr** to the UI via polling, and serves a **ZIP** when the job succeeds.

Intended for a **school/lab server**: bind address defaults to **`127.0.0.1`** — use **SSH port forwarding** to reach it from your laptop. Do not expose it to the public internet without hardening.

## Current features

- **Web UI** — single page: upload, optional username, GPU status/selector, task history, status + live logs, ZIP download when ready.
- **Upload** — `POST /upload` saves the file under `uploads/` (UUID-prefixed name), creates a task (`uploaded`).
- **Async run** — `POST /run/<task_id>` queues work and starts `bash scripts/whole.sh <sequence_stem> <gpu_id>` in a **non-blocking** thread (same process).
- **Pipeline entry** — `scripts/whole.sh` is the main entry; it runs your real steps (VHAP preprocessing/track/export, GaussianAvatars `train.py`, etc.) and, on success, **builds a ZIP** of the training output into `results/zip_res/<sequence>.zip`.
- **Live logs** — stdout/stderr from the shell and child Python processes are captured incrementally; the UI polls **`GET /status/<task_id>`** about every 2s. Logs are capped for UI size (`MAX_TASK_LOG_LINES`, `MAX_LOG_LENGTH` in `config.py`).
- **ZIP download** — when the script exits successfully and the expected ZIP exists, the task is **`success`** with **`download_ready`**. **`GET /download/<task_id>`** sends the file; the UI shows a download control.
- **Disk persistence** — task metadata in `data/tasks.json`; full combined log stream in `data/logs/<task_id>.log`. On server **restart**, tasks that were **`running`** become **`interrupted`**.
- **Task list** — `GET /tasks?username=<name>` (UI uses a username field; default bucket is `default`).
- **GPU (optional)** — `GET /gpu/status` uses **`nvidia-smi`** when available. Upload/run accept **`gpu`** query params; the UI can pick a GPU before upload/start.

## Requirements

- **Python 3.10+** (code uses modern typing; adjust if needed)
- **Linux** with **`bash`**
- Whatever **`whole.sh`** needs (conda env, sibling repos such as VHAP / GaussianAvatars, CUDA, etc. — see `scripts/whole.sh`)
- **`zip`** on the server for the packaging step inside `whole.sh`
- **`nvidia-smi`** only if you want the GPU status panel to show real data (otherwise the UI falls back safely)

## Project structure (important paths)

```
web_runner/
  app.py                 # Flask app, routes, subprocess + log streaming, persistence
  config.py              # Paths, upload limit, log caps, data/ paths, default GPU
  task_manager.py        # In-memory task dict + helpers (loaded from disk at startup)
  requirements.txt
  data/
    tasks.json           # Persisted task metadata (created at runtime)
    logs/<task_id>.log   # Full persisted log lines (created when a run starts)
  uploads/               # Uploaded videos
  results/zip_res/       # ZIP artifacts produced by the pipeline (expected by the app)
  scripts/whole.sh       # Main pipeline entry (called by the backend)
  templates/index.html   # UI
  static/app.js          # Upload, run, poll, history, GPU controls
  static/style.css
```

## Setup

```bash
cd web_runner
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Ensure directories exist (the app creates most of them on startup; you still need a working `whole.sh` and pipeline layout):

```bash
mkdir -p uploads results/zip_res
# whole.sh must be runnable (often: chmod +x scripts/whole.sh)
```

## Run locally / on the server

```bash
python app.py
```

Default: **`http://127.0.0.1:5000`**. Change `HOST` / `PORT` in `config.py` if needed.

### Access from your laptop (SSH forwarding)

```bash
ssh -L 5000:localhost:5000 user@your-server
```

Then open **`http://localhost:5000`** in your browser.

## Main request flow

1. **Browser** loads the page (`GET /`).
2. **Optional:** UI loads GPU info (`GET /gpu/status`) and task list (`GET /tasks?username=...`).
3. **Upload** — `POST /upload?username=...&gpu=...` (form field **`video`**). File saved under `uploads/`; response includes **`task_id`**, status **`uploaded`**.
4. **Start** — `POST /run/<task_id>?gpu=...`. Task moves to **`queued`** then **`running`**; `whole.sh` runs in a daemon thread.
5. **Poll** — `GET /status/<task_id>` returns JSON including **`task.stdout`**, **`task.stderr`**, **`status`**, **`error_message`**, **`download_ready`**, etc. The UI stops polling when the task is **`success`** or **`failed`**. A task may show **`interrupted`** if the server was restarted while it was **`running`**.
6. **Download** — when **`success`** and **`download_ready`**, open **`GET /download/<task_id>`** (or use the UI button).

### API summary (implemented)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | HTML UI |
| GET | `/gpu/status` | JSON GPU snapshot (`nvidia-smi` or safe fallback) |
| POST | `/upload` | Multipart `video`; query `username`, optional `gpu` |
| POST | `/run/<task_id>` | Start async job; query `gpu` (defaults if omitted) |
| GET | `/status/<task_id>` | Task + tail of logs from disk |
| GET | `/tasks?username=` | List tasks for that username |
| GET | `/download/<task_id>` | ZIP file when task completed successfully |

## Notes on `whole.sh`

- The backend does **not** embed pipeline logic in Python — it invokes **`scripts/whole.sh`** with the **sequence name** (stem of the stored upload filename) and **GPU index** as **argv** (`$1`, `$2`).
- **`CUDA_VISIBLE_DEVICES`** and training paths are handled inside `whole.sh` and the Python scripts it calls.
- The **ZIP** path the app expects is **`results/zip_res/<sequence_stem>.zip`** under `web_runner` (aligned with `config.RESULTS_FOLDER`).

## Troubleshooting

- **Script not found** — `config.SCRIPT_PATH` must point to `scripts/whole.sh`.
- **Run fails / non-zero exit** — Check live **`stderr`** in the UI and `error_message` on the task; run `whole.sh` manually with the same arguments to debug.
- **Success but no download** — ZIP missing at `results/zip_res/<stem>.zip` or pipeline exited non-zero.
- **Port in use** — Change `PORT` in `config.py` or free port 5000.
- **Large uploads** — `MAX_CONTENT_LENGTH` is 2GB in `config.py`.
- **Logs look short** — By design: rolling line cap + character truncation in `config.py`.
- **Restart during a run** — That task is marked **`interrupted`** in `data/tasks.json`; re-upload for a fresh run if needed.

## Summary of README changes (this edit)

- Replaced outdated **`run_pipeline.sh`** references with **`scripts/whole.sh`** and the real async + ZIP flow.
- Documented **live log streaming**, **ZIP under `results/zip_res`**, **`GET /download`**, and **disk persistence** (`data/tasks.json`, `data/logs/`, interrupted-on-restart).
- Listed **implemented** endpoints including **`/gpu/status`**, **`/tasks`**, and **`gpu` / `username` query params**.
- Trimmed speculative “future” items; kept practical structure, run instructions, and troubleshooting aligned with the current code.
