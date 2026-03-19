from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, Optional

# In-memory task store for MVP (will be replaced later if needed).
TASKS: Dict[str, Dict[str, Any]] = {}
_LOCK = Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def truncate_text(text: Optional[str], max_len: int) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    keep = max_len - 80
    if keep < 0:
        keep = 0
    return (
        text[:keep]
        + "\n... [truncated] ...\n"
        + text[-min(len(text), 60) :]
    )


def create_task(
    task_id: str,
    filename: str,
    file_path: str,
    status: str = "uploaded",
) -> Dict[str, Any]:
    # 创建任务字典，包含taskid、文件名、文件路径、状态、创建时间、开始运行时间、
    # 结束时间、返回码、标准输出、标准错误、错误信息、输出路径、输出文件名、下载准备、结果信息
    task: Dict[str, Any] = {
        "task_id": task_id,
        "filename": filename,
        "file_path": file_path,
        "status": status,
        "created_at": _now_iso(),
        "started_at": None,
        "finished_at": None,
        "return_code": None,
        "stdout": "",
        "stderr": "",
        "error_message": None,
        "output_path": None,
        "output_filename": None,
        "download_ready": False,
        "result_message": None,
    }
    with _LOCK:
        TASKS[task_id] = task
        return dict(task)


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        task = TASKS.get(task_id)
        return dict(task) if task else None


def update_task(task_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    with _LOCK:
        task = TASKS.get(task_id)
        if not task:
            return None
        task.update(fields)
        return dict(task)


def can_run_task(task_id: str) -> bool:
    with _LOCK:
        task = TASKS.get(task_id)
        if not task:
            return False
        return task.get("status") == "uploaded"

