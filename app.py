from __future__ import annotations

import logging
import subprocess
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

import config
import task_manager


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

    # Ensure expected folders exist (safe if already present).
    config.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    config.RESULTS_FOLDER.mkdir(parents=True, exist_ok=True)

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
        task_manager.create_task(
            task_id=task_id,
            filename=safe_name,
            file_path=str(saved_path),
            status="uploaded",
        )

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
            try:
                # 子进程运行脚本
                # 调用脚本的地方
                # bash 脚本路径 输入文件路径 输出文件路径
                proc = subprocess.Popen(
                    ["bash", str(config.SCRIPT_PATH), fpath, str(gpu)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                # 使用subprocess.PIPE将标准输出和标准错误重定向到管道
                # 使用proc.communicate()等待子进程完成
                out, err = proc.communicate()
                # 获取子进程的返回码
                rc = proc.returncode
                # 截断标准输出和标准错误，避免过长
                out_t = task_manager.truncate_text(out, config.MAX_LOG_LENGTH)
                err_t = task_manager.truncate_text(err, config.MAX_LOG_LENGTH)
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
        task = task_manager.get_task(task_id)
        if not task:
            return jsonify({"success": False, "error": "task not found"}), 404
        return jsonify({"success": True, "task": task}), 200

    @app.get("/download/<task_id>")
    def download(task_id: str):
        task = task_manager.get_task(task_id)
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

