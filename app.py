from __future__ import annotations

import logging
import json
import os
from collections import deque
import subprocess
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

import config
import task_manager

TASKS_JSON_LOCK = threading.Lock()

LOG_PREFIX_STDOUT = "STDOUT:"
LOG_PREFIX_STDERR = "STDERR:"


def _read_tasks_json_unlocked() -> dict[str, dict]:
    if not config.TASKS_JSON_PATH.exists():
        return {}
    try:
        with open(config.TASKS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _write_tasks_json_unlocked(tasks: dict[str, dict]) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = config.TASKS_JSON_PATH.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, config.TASKS_JSON_PATH)


def _persist_task_full(task: dict) -> None:
    task_id = task.get("task_id")
    if not task_id:
        return
    with TASKS_JSON_LOCK:
        tasks = _read_tasks_json_unlocked()
        tasks[str(task_id)] = task
        _write_tasks_json_unlocked(tasks)


def _persist_task_fields(task_id: str, fields: dict) -> None:
    with TASKS_JSON_LOCK:
        tasks = _read_tasks_json_unlocked()
        task = tasks.get(task_id) or {"task_id": task_id}
        task.update(fields)
        tasks[task_id] = task
        _write_tasks_json_unlocked(tasks)


def _get_task_from_disk(task_id: str) -> dict | None:
    with TASKS_JSON_LOCK:
        tasks = _read_tasks_json_unlocked()
        return tasks.get(task_id)


def _read_last_task_logs(task_id: str) -> tuple[str, str]:
    stdout_lines: deque[str] = deque(maxlen=config.MAX_TASK_LOG_LINES)
    stderr_lines: deque[str] = deque(maxlen=config.MAX_TASK_LOG_LINES)

    log_path = config.LOGS_DIR / f"{task_id}.log"
    if not log_path.exists():
        return "", ""

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith(LOG_PREFIX_STDOUT):
                    stdout_lines.append(line[len(LOG_PREFIX_STDOUT) :])
                elif line.startswith(LOG_PREFIX_STDERR):
                    stderr_lines.append(line[len(LOG_PREFIX_STDERR) :])
    except Exception:
        return "", ""

    stdout = "".join(stdout_lines)
    stderr = "".join(stderr_lines)
    return (
        task_manager.truncate_text(stdout, config.MAX_LOG_LENGTH),
        task_manager.truncate_text(stderr, config.MAX_LOG_LENGTH),
    )


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

    # Ensure expected folders exist (safe if already present).
    config.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    config.RESULTS_FOLDER.mkdir(parents=True, exist_ok=True)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Recovery: load persisted tasks and interrupt any in-flight runs.
    persisted_tasks: dict[str, dict] = {}
    with TASKS_JSON_LOCK:
        persisted_tasks = _read_tasks_json_unlocked()
        changed = False
        now_iso = task_manager._now_iso()
        for _, t in persisted_tasks.items():
            if t.get("status") == "running":
                t["status"] = "interrupted"
                t["finished_at"] = now_iso
                t.setdefault("error_message", "Task interrupted due to server restart.")
                changed = True
        if changed:
            _write_tasks_json_unlocked(persisted_tasks)

    with task_manager._LOCK:
        task_manager.TASKS.clear()
        task_manager.TASKS.update({str(k): v for k, v in persisted_tasks.items()})

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.post("/upload")
    def upload():
        # 检测传输是否完整
        if "video" not in request.files:
            return jsonify({"success": False, "error": "missing file field 'video'"}), 400

        # 检测文件是否存在
        file = request.files["video"]
        if not file or file.filename is None or file.filename.strip() == "":
            return jsonify({"success": False, "error": "empty filename"}), 400

        # 检测文件扩展名是否符合要求
        original_name = file.filename
        safe_name = secure_filename(original_name)
        ext = Path(safe_name).suffix.lower()
        if ext not in config.ALLOWED_EXTENSIONS:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"extension not allowed: {ext or '(none)'}",
                    }
                ),
                400,
            )

        # 生成文件名，加上随机UUID
        file_uuid = uuid.uuid4().hex
        stored_name = f"{file_uuid}_{safe_name}"
        saved_path = config.UPLOAD_FOLDER / stored_name
        file.save(str(saved_path))

        base_path = config.BASE_DIR.resolve()
        # print(f"DEBUG: Base is {config.BASE_DIR}")
        # print(f"DEBUG: Saved is {saved_path}")
        display_path = saved_path.resolve()
        display_path = display_path.relative_to(base_path).as_posix()
        
        task_id = str(uuid.uuid4())
        created_task = task_manager.create_task(
            task_id=task_id,
            filename=safe_name,
            file_path=str(saved_path),
            status="uploaded",
        )
        created_task["username"] = request.args.get("username") or "default"
        _persist_task_full(created_task)

        return (
            jsonify(
                {
                    "success": True,
                    "task_id": task_id,
                    "filename": safe_name,
                    "file_path": str(display_path),
                    "status": "uploaded",
                }
            ),
            200,
        )

    @app.post("/run/<task_id>")
    def run_task(task_id: str):
        # 检测任务是否存在
        task = task_manager.get_task(task_id)
        if not task:
            return jsonify({"success": False, "error": "task not found"}), 404
        # 正常来说task在后端此时是 uploaded 状态。
        # 如果任务不是uploaded状态，就分类判断返回信息
        if not task_manager.can_run_task(task_id):
            # 检测任务状态
            status = task.get("status")
            # 如果是排队中或者正在跑，则当前无法执行
            if status in ("queued", "running"):
                return (
                    jsonify({"success": False, "error": f"task already {status}"}),
                    409,
                )
            # 如果是成功或者失败，则当前无法执行
            if status in ("success", "failed"):
                return (
                    jsonify(
                        {"success": False, "error": f"task already finished ({status})"}
                    ),
                    409,
                )
            # 如果是其他状态，则当前无法执行
            return (
                jsonify({"success": False, "error": f"task not runnable (status={status})"}),
                409,
            )

        # 检测脚本是否存在
        if not config.SCRIPT_PATH.exists():
            return jsonify({"success": False, "error": "script not found"}), 500

        # 获取task对应的上传视频文件路径
        file_path = task.get("file_path")
        # 如果任务没有文件路径，则返回错误
        if not file_path:
            return jsonify({"success": False, "error": "task missing file_path"}), 500

        seq_name = Path(file_path).stem
        # 生成结果文件名和路径
        result_filename = f"{seq_name}.zip"
        result_path = config.RESULTS_FOLDER / result_filename

        # 如果一切正常，则准备开始运行脚本。更新任务状态为排队中，清除错误信息，并记录输出路径
        task_manager.update_task(
            task_id,
            status="queued",
            error_message=None,
            output_path=str(result_path),
            output_filename=result_filename,
            download_ready=False,
            result_message=None,
        )
        _persist_task_fields(
            task_id,
            {
                "status": "queued",
                "error_message": None,
                "output_path": str(result_path),
                "output_filename": result_filename,
                "download_ready": False,
                "result_message": None,
            },
        )
        # 定义一个内部函数，用于运行脚本。该函数会在后台线程中运行。
        def _runner(tid: str, fpath: str, gpu: int, rpath: str) -> None:
            # 更新任务状态为正在运行，清除错误信息，记录开始运行时间
            task_manager.update_task(
                tid,
                status="running",
                started_at=task_manager._now_iso(),  # MVP: keep helper in task_manager
                stdout="",
                stderr="",
                return_code=None,
                finished_at=None,
                error_message=None,
                download_ready=False,
                result_message=None,
            )
            _persist_task_fields(
                tid,
                {
                    "status": "running",
                    "started_at": task_manager._now_iso(),
                    "error_message": None,
                    "download_ready": False,
                    "result_message": None,
                    "return_code": None,
                    "finished_at": None,
                },
            )
            try:
                # 子进程运行脚本
                # 调用脚本的地方
                # bash 脚本路径 输入文件路径 输出文件路径
                out_lines: list[str] = []
                err_lines: list[str] = []
                out_lock = threading.Lock()
                err_lock = threading.Lock()

                log_path = config.LOGS_DIR / f"{tid}.log"
                with open(log_path, "w", encoding="utf-8"):
                    pass
                log_write_lock = threading.Lock()

                child_env = os.environ.copy()
                # Make python scripts invoked by whole.sh flush output promptly.
                child_env["PYTHONUNBUFFERED"] = "1"

                proc = subprocess.Popen(
                    ["bash", str(config.SCRIPT_PATH), fpath, str(gpu)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    env=child_env,
                )

                def _stream_output(
                    stream, lines: list[str], lock: threading.Lock, field: str
                ) -> None:
                    if stream is None:
                        return
                    prefix = LOG_PREFIX_STDOUT if field == "stdout" else LOG_PREFIX_STDERR
                    with open(log_path, "a", encoding="utf-8", errors="replace", buffering=1) as log_fh:
                        for line in iter(stream.readline, ""):
                            with lock:
                                lines.append(line)
                                # Enforce a rolling line limit so the frontend stays readable.
                                if len(lines) > config.MAX_TASK_LOG_LINES:
                                    del lines[: len(lines) - config.MAX_TASK_LOG_LINES]
                                joined = "".join(lines)
                            with log_write_lock:
                                log_fh.write(prefix + line)
                            task_manager.update_task(
                                tid,
                                **{
                                    field: task_manager.truncate_text(
                                        joined, config.MAX_LOG_LENGTH
                                    )
                                },
                            )
                    stream.close()

                stdout_thread = threading.Thread(
                    target=_stream_output,
                    args=(proc.stdout, out_lines, out_lock, "stdout"),
                    daemon=True,
                )
                stderr_thread = threading.Thread(
                    target=_stream_output,
                    args=(proc.stderr, err_lines, err_lock, "stderr"),
                    daemon=True,
                )
                stdout_thread.start()
                stderr_thread.start()
                proc.wait()
                stdout_thread.join()
                stderr_thread.join()
                # 获取子进程的返回码
                rc = proc.returncode
                # 截断标准输出和标准错误，避免过长
                with out_lock:
                    out_t = task_manager.truncate_text(
                        "".join(out_lines), config.MAX_LOG_LENGTH
                    )
                with err_lock:
                    err_t = task_manager.truncate_text(
                        "".join(err_lines), config.MAX_LOG_LENGTH
                    )
                # 检测结果文件是否存在
                result_file_exists = Path(rpath).is_file()
                # 如果返回码为0且结果文件存在，则任务成功
                if rc == 0 and result_file_exists:
                    status = "success"
                    error_message = None
                    download_ready = True
                    result_message = "Result file generated."
                # 如果返回码为0且结果文件不存在，则任务失败
                elif rc == 0 and not result_file_exists:
                    status = "failed"
                    error_message = "script returned zero exit code but result file missing"
                    result_message = "Script finished but result file was not generated."
                    download_ready = False
                # 如果返回码不为0，则任务失败
                else:
                    status = "failed"
                    error_message = "script returned non-zero exit code"
                    result_message = "Script failed."
                    download_ready = False
                
                # 更新任务状态
                task_manager.update_task(
                    tid,
                    status=status,
                    finished_at=task_manager._now_iso(),
                    return_code=rc,
                    stdout=out_t,
                    stderr=err_t,
                    error_message=error_message,
                    download_ready=download_ready,
                    result_message=result_message,
                )
                _persist_task_fields(
                    tid,
                    {
                        "status": status,
                        "finished_at": task_manager._now_iso(),
                        "return_code": rc,
                        "error_message": error_message,
                        "download_ready": download_ready,
                        "result_message": result_message,
                        "stdout": out_t,
                        "stderr": err_t,
                    },
                )
            except Exception as e:
                logging.exception(
                    "run_task _runner failed task_id=%s path=%s gpu=%s",
                    tid,
                    fpath,
                    gpu,
                )
                task_manager.update_task(
                    tid,
                    status="failed",
                    finished_at=task_manager._now_iso(),
                    return_code=None,
                    stdout="",
                    stderr="",
                    error_message=str(e),
                    download_ready=False,
                    result_message="Script execution raised an exception.",
                )
                _persist_task_fields(
                    tid,
                    {
                        "status": "failed",
                        "finished_at": task_manager._now_iso(),
                        "return_code": None,
                        "error_message": str(e),
                        "download_ready": False,
                        "result_message": "Script execution raised an exception.",
                        "stdout": "",
                        "stderr": "",
                    },
                )

        # 创建一个后台线程来运行脚本_runner
        # 参数：任务id、输入文件路径、输出文件路径
        # daemon=True表示后台线程
        thread = threading.Thread(
            # target=_runner, args=(task_id, str(file_path), str(result_path)), daemon=True
            target=_runner, args=(task_id, str(seq_name), 5, str(result_path)), daemon=True
        )
        # 启动线程
        thread.start()

        return jsonify({"success": True, "task_id": task_id, "status": "queued"}), 200

    @app.get("/status/<task_id>")
    def status(task_id: str):
        task = _get_task_from_disk(task_id)
        if not task:
            return jsonify({"success": False, "error": "task not found"}), 404
        stdout, stderr = _read_last_task_logs(task_id)
        task["stdout"] = stdout
        task["stderr"] = stderr
        return jsonify({"success": True, "task": task}), 200

    @app.get("/tasks")
    def tasks_by_username():
        username = request.args.get("username") or "default"
        with TASKS_JSON_LOCK:
            tasks = _read_tasks_json_unlocked()
            filtered = [
                t
                for t in tasks.values()
                if (t.get("username") or "default") == username
            ]
        return jsonify({"success": True, "tasks": filtered}), 200

    @app.get("/download/<task_id>")
    def download(task_id: str):
        task = _get_task_from_disk(task_id)
        if not task:
            return jsonify({"success": False, "error": "task not found"}), 404

        status = (task.get("status") or "").lower()
        download_ready = bool(task.get("download_ready"))
        if status != "success" or not download_ready:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "task is not completed successfully or download not ready",
                    }
                ),
                400,
            )

        output_path = task.get("output_path")
        output_filename = task.get("output_filename") or f"{task_id}_result.zip"
        if not output_path:
            return (
                jsonify(
                    {"success": False, "error": "result file path not recorded for task"}
                ),
                500,
            )

        path_obj = Path(output_path)
        if not path_obj.is_file():
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "result file missing on server",
                    }
                ),
                500,
            )

        return send_file(
            str(path_obj),
            as_attachment=True,
            download_name=output_filename,
        )

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)

