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

