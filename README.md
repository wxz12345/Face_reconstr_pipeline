# Web Runner (Flask MVP)

A minimal Flask web app to:

- Upload a video from your browser (saved into `uploads/`)
- Click “Start Processing” to run `scripts/run_pipeline.sh` **asynchronously**
- Poll task status from the browser until the job is done (`uploaded → queued → running → success|failed`)
- View `stdout`/`stderr` captured from the script

This is an MVP intended for a **Linux school server**. It is meant to be accessed via **SSH port forwarding** and **not exposed to the public internet**. The server binds to `127.0.0.1` only.

## Requirements

- **Python 3.9+**
- A shell environment that can run `bash`

## Project structure

```
web_runner/
  app.py                  # Flask app + API endpoints
  config.py               # Paths and limits (upload folder, script path, 2GB limit)
  task_manager.py         # In-memory task store + helpers
  requirements.txt        # Python dependencies (minimal)
  uploads/                # Uploaded videos saved here
  scripts/run_pipeline.sh # The script that processes one uploaded file
  templates/index.html    # Single-page UI (no frameworks)
  static/app.js           # Calls /upload, /run, polls /status
  static/style.css        # Simple card UI + status badges
```

## Setup (on the school server)

From the repo/workspace root:

```bash
cd web_runner
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Ensure required paths exist:

```bash
mkdir -p uploads
ls -la scripts/run_pipeline.sh
```

Make the script executable:

```bash
chmod +x scripts/run_pipeline.sh
```

## Run (server-side)

Start Flask:

```bash
python app.py
```

By default it listens on **`127.0.0.1:5000`** (server-local only).

### Quick server-local test

On the server:

```bash
curl http://127.0.0.1:5000
```

You should get HTML back (HTTP 200).

## Access from your personal computer (IMPORTANT)

Because the server binds to `127.0.0.1`, you must use SSH port forwarding.

From your personal computer:

```bash
ssh -L 5000:localhost:5000 xwangke@eez214.ece.ust.hk
```

Then open this on your personal computer:

- `http://localhost:5000`

Keep the SSH session open while you use the web page.

## Usage flow

1. Open `http://localhost:5000` (through SSH port forwarding).
2. Select a video file (`.mp4`, `.mov`, `.avi`, `.mkv`).
3. Click **Upload**.
   - The backend saves the file into `uploads/` with a UUID prefix.
   - You’ll see `task_id`, `filename`, `file_path`, and status `uploaded`.
4. Click **Start Processing**.
   - The backend runs `bash scripts/run_pipeline.sh <file_path>` in a background thread.
   - The UI polls `/status/<task_id>` every 2 seconds.
5. Watch status and logs.
   - Polling stops automatically when status becomes `success` or `failed`.

## Troubleshooting

- **Port already in use (5000)**:
  - Error looks like “Address already in use” / “Port 5000 is in use”.
  - Fix: stop the process using port 5000 or change `PORT` in `config.py`.

- **Forgot SSH port forwarding**:
  - Symptom: browser can’t connect to `http://localhost:5000` on your personal computer.
  - Fix: run `ssh -L 5000:localhost:5000 xwangke@your_school_server` and keep it open.

- **Script not found**:
  - Symptom: `/run/<task_id>` returns `{"success":false,"error":"script not found"}`.
  - Fix: confirm `scripts/run_pipeline.sh` exists at that exact path.

- **Script not executable**:
  - Symptom: run fails; `stderr` may mention “Permission denied”.
  - Fix: `chmod +x scripts/run_pipeline.sh`.

- **Uploads directory permission denied**:
  - Symptom: upload fails with a server error, or file can’t be saved.
  - Fix: ensure `uploads/` exists and is writable by your user (`mkdir -p uploads`, check permissions).

- **File too large**:
  - Symptom: upload fails (often with HTTP 413) for very large files.
  - Cause: `MAX_CONTENT_LENGTH` in `config.py` (currently 2GB).
  - Fix: upload a smaller file or raise the limit (server memory/storage permitting).

- **task_id not found**:
  - Symptom: `/status/<task_id>` or `/run/<task_id>` returns 404 with `task not found`.
  - Cause: tasks are stored **in memory**; restarting `python app.py` clears all tasks.
  - Fix: re-upload and use the new `task_id`.

- **Duplicate run attempt**:
  - Symptom: `/run/<task_id>` returns 409 like “task already running/queued” or “task already finished”.
  - MVP behavior: a task can be run only once.
  - Fix: upload again to create a new task.

- **Upload succeeds but run fails**:
  - Check `stderr` and `error_message` in the status panel.
  - Common causes: missing dependencies inside `run_pipeline.sh`, wrong file path, script errors.
  - Tip: run the script manually on the server to debug:
    - `bash scripts/run_pipeline.sh /absolute/path/to/uploaded_file`

- **stdout/stderr truncated (by design)**:
  - The backend truncates captured logs to `MAX_LOG_LENGTH` (see `config.py`) to keep responses small.

## Future extensions (if you need more than an MVP)

- Persist tasks in a **database** (so restarts don’t lose task state)
- Use a real **task queue** (Celery/RQ/Sidekiq-like) instead of threads
- Production deployment with **Gunicorn + Nginx** (and proper systemd service)
- Add **authentication** (at minimum, password protection) before any broader access
- **Auto-trigger processing** immediately after upload
- Allow **output file download** from the UI
- Integrate a real **video pipeline** (ffmpeg/transcoding, ML inference, etc.)

