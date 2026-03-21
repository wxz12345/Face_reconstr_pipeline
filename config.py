from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
RESULTS_FOLDER = BASE_DIR / "results/zip_res"
SCRIPT_PATH = BASE_DIR / "scripts" / "whole.sh"

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi"}
MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2GB

HOST = "127.0.0.1"
PORT = 5000
DEBUG = False

MAX_LOG_LENGTH = 200_000

# Keep only the latest N log lines for task stdout/stderr.
# This is enforced as a rolling window during streaming, so polling stays readable.
MAX_TASK_LOG_LINES = 100

# Disk-backed persistence (used for recovery after server restart).
DATA_DIR = BASE_DIR / "data"
TASKS_JSON_PATH = DATA_DIR / "tasks.json"
LOGS_DIR = DATA_DIR / "logs"

# Default GPU index when the client omits `gpu` or detection fails.
DEFAULT_GPU_ID = 0

