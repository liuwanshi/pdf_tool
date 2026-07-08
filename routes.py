"""Flask 路由注册"""

import json
import logging
import os
import time
import uuid

from flask import (
    Flask, render_template, request, jsonify, send_file, abort, g,
)

from config import UPLOAD_FOLDER, RESULT_FOLDER
from models import create_task, get_task, get_tasks_paginated, delete_task as db_delete_task, count_tasks_by_input_path
from tasks import run_task, run_ocr_task, run_batch_ocr_task, is_worker_alive, compress_task, split_task, merge_task
from utils.file_utils import validate_file, validate_batch_files, save_upload

logger = logging.getLogger(__name__)


def register_routes(app: Flask) -> None:
    """注册所有路由到 Flask 应用"""

    # ======== 统一请求日志（before / after hooks） ========

    @app.before_request
    def _log_request_entry():
        """记录 API 请求入口（仅 /api/ 和 /upload/ 路径）"""
        if request.path.startswith("/api/") or request.path.startswith("/upload/"):
            g.request_start = time.perf_counter()
            # 脱敏：不记录文件内容，只记录请求元信息
            logger.info(
                f"请求开始: {request.method} {request.path}"
                + (f"?{request.query_string.decode('utf-8')}" if request.query_string else "")
            )

    @app.after_request
    def _log_request_exit(response):
        """记录 API 请求出口（状态码 + 耗时）"""
        if request.path.startswith("/api/") or request.path.startswith("/upload/"):
            elapsed = 0
            if hasattr(g, "request_start"):
                elapsed = (time.perf_counter() - g.request_start) * 1000
            logger.info(
                f"请求完成: {request.method} {request.path} → {response.status_code} ({elapsed:.0f}ms)"
            )
            # 慢请求告警：超过 3 秒输出 WARNING
            if elapsed > 3000:
                logger.warning(f"慢请求: {request.method} {request.path} 耗时 {elapsed:.0f}ms")
            # 高频轮询端点降级为 DEBUG（/api/tasks 每 3s 轮询一次）
            if request.path == "/api/tasks":
                for handler in logger.handlers:
                    record = logging.LogRecord(
                        logger.name, logging.DEBUG, request.path, 0,
                        f"轮询刷新 (HTTP {response.status_code})", None, None
                    )
        return response

    # ======== 页面路由 ========

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/batch")
    def batch():
        return render_template("batch.html")

    @app.route("/tasks")
    def tasks_page():
        return render_template("tasks.html")

    # ======== 上传路由 ========

    @app.route("/upload/single", methods=["POST"])
    def upload_single():
        file = request.files.get("file")
        error = validate_file(file)
        if error:
            logger.warning(f"单文件上传被拒: {error}")
            return jsonify({"error": error}), 400

        filepath = save_upload(file, UPLOAD_FOLDER)
        logger.info(f"单文件上传成功: {file.filename} → {filepath}")
        return jsonify({"filepath": filepath, "filename": file.filename})

    @app.route("/upload/batch", methods=["POST"])
    def upload_batch():
        files = request.files.getlist("files")
        error = validate_batch_files(files)
        if error:
            logger.warning(f"批量上传被拒: {error}")
            return jsonify({"error": error}), 400

        results = []
        for f in files:
            if f and f.filename:
                filepath = save_upload(f, UPLOAD_FOLDER)
                results.append({"filepath": filepath, "filename": f.filename})
        logger.info(f"批量上传成功: {len(results)} 个文件")
        return jsonify({"files": results})

    # ======== 任务 API ========

    @app.route("/api/task/create", methods=["POST"])
    def api_create_task():
        """创建处理任务"""
        data = request.get_json() or {}
        task_type = data.get("task_type")

        if not task_type:
            return jsonify({"error": "缺少 task_type"}), 400

        try:
            task_id = _create_and_run_task(task_type, data)
            logger.info(f"任务创建成功: task_id={task_id}, type={task_type}")
            return jsonify({"task_id": task_id})
        except ValueError as e:
            logger.warning(f"任务创建参数错误: {e}")
            return jsonify({"error": str(e)}), 400
        except Exception:
            logger.exception(f"任务创建异常: type={task_type}, data={data}")
            return jsonify({"error": "创建任务失败，请查看日志"}), 500

    @app.route("/api/task/<task_id>")
    def api_get_task(task_id):
        task = get_task(task_id)
        if task is None:
            return jsonify({"error": "任务不存在"}), 404
        return jsonify(task)

    @app.route("/api/tasks")
    def api_get_tasks():
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)
        result = get_tasks_paginated(page=page, per_page=per_page)
        return jsonify(result)

    @app.route("/api/task/<task_id>/retry", methods=["POST"])
    def api_retry_task(task_id):
        """重试失败或中断的任务"""
        task = get_task(task_id)
        if task is None:
            return jsonify({"error": "任务不存在"}), 404

        retryable = {"failed", "interrupted"}
        if task["status"] not in retryable:
            return jsonify({"error": f"只能重试失败或中断的任务，当前状态: {task['status']}"}), 400

        # 检查 worker 子进程是否仍在运行
        if is_worker_alive(task_id):
            return jsonify({
                "error": "该任务的 worker 子进程仍在后台运行，请等待其完成后再重试",
            }), 409

        # 再次读取最新状态
        task = get_task(task_id)
        if task and task["status"] == "completed":
            return jsonify({
                "error": "该任务已在后台完成，无需重试",
                "task_id": task_id,
            }), 409

        input_path = task.get("input_path", "")
        task_params_str = task.get("task_params", "")

        if not input_path or not os.path.isfile(input_path):
            return jsonify({"error": "原始文件已不存在，无法重试"}), 400

        try:
            params = json.loads(task_params_str) if task_params_str else {}
            data = {
                "filepath": input_path,
                "filename": task["original_filename"],
                **params,
            }
            new_task_id = _create_and_run_task(task["task_type"], data)
            logger.info(f"任务重试: 原={task_id}, 新={new_task_id}")
            return jsonify({
                "task_id": new_task_id,
                "message": f"原任务 {task_id[:8]}... 已重新提交",
            })
        except ValueError as e:
            logger.warning(f"重试参数错误: task_id={task_id}, error={e}")
            return jsonify({"error": str(e)}), 400
        except Exception:
            logger.exception(f"重试异常: task_id={task_id}")
            return jsonify({"error": "重试失败，请查看日志"}), 500

    @app.route("/api/task/<task_id>", methods=["DELETE"])
    def api_delete_task(task_id):
        """删除任务记录及其关联文件"""
        task = get_task(task_id)
        if task is None:
            return jsonify({"error": "任务不存在"}), 404

        if task["status"] == "processing":
            return jsonify({"error": "处理中的任务无法删除，请等待完成或中断后再删除"}), 400

        # 清理结果目录
        result_dir = os.path.join(RESULT_FOLDER, task_id)
        if os.path.isdir(result_dir):
            _rmtree_safe(result_dir)

        # 清理上传文件（仅当无其他任务引用时）
        input_path = task.get("input_path", "")
        if input_path and os.path.isfile(input_path):
            ref_count = count_tasks_by_input_path(input_path, exclude_task_id=task_id)
            if ref_count == 0:
                try:
                    os.remove(input_path)
                    logger.info(f"已清理上传文件: {input_path}")
                except OSError:
                    pass

        db_delete_task(task_id)
        logger.info(f"已删除任务: {task_id}")
        return jsonify({"message": "已删除", "task_id": task_id})


    def _rmtree_safe(path: str) -> None:
        """安全递归删除目录"""
        for root, dirs, files in os.walk(path, topdown=False):
            for name in files:
                filepath = os.path.join(root, name)
                try:
                    os.unlink(filepath)
                except OSError:
                    logger.debug(f"删除文件失败: {filepath}")
            for name in dirs:
                dirpath = os.path.join(root, name)
                try:
                    os.rmdir(dirpath)
                except OSError:
                    logger.debug(f"删除目录失败: {dirpath}")
        try:
            os.rmdir(path)
        except OSError:
            logger.debug(f"删除目录失败: {path}")


    # ======== 下载路由 ========

    @app.route("/download/<task_id>")
    def download_result(task_id):
        task = get_task(task_id)
        if task is None or task["status"] != "completed":
            abort(404)

        result_path = task.get("result_path")
        result_filename = task.get("result_filename", "result")

        if not result_path or not os.path.isfile(result_path):
            abort(404)

        logger.info(f"下载结果: task_id={task_id}, file={result_filename}")
        return send_file(
            result_path,
            as_attachment=True,
            download_name=result_filename,
        )


def _create_and_run_task(task_type: str, data: dict) -> str:
    """根据任务类型创建任务记录并提交后台执行，返回 task_id"""
    if task_type == "ocr":
        filepath = data.get("filepath")
        filename = data.get("filename") or os.path.basename(filepath)
        if not filepath:
            raise ValueError("缺少 filepath")
        task_id = create_task(filename, "ocr", input_path=filepath)
        run_ocr_task(task_id, filepath, filename)
        return task_id

    elif task_type == "compress":
        filepath = data.get("filepath")
        filename = data.get("filename") or os.path.basename(filepath)
        target_kb = data.get("target_kb")
        if target_kb is not None:
            target_kb = float(target_kb)
        if not filepath:
            raise ValueError("缺少 filepath")
        task_params = {"target_kb": target_kb} if target_kb else None
        task_id = create_task(filename, "compress", input_path=filepath,
                              task_params=task_params)
        run_task(task_id, compress_task, task_id, filepath, filename, target_kb)
        return task_id

    elif task_type == "split":
        filepath = data.get("filepath")
        filename = data.get("filename") or os.path.basename(filepath)
        mode = data.get("mode", "range")
        page_range = data.get("page_range")
        if not filepath:
            raise ValueError("缺少 filepath")
        task_params = {"mode": mode, "page_range": page_range}
        task_id = create_task(filename, "split", input_path=filepath,
                              task_params=task_params)
        compress_targets = data.get("compress_targets")
        run_task(task_id, split_task, task_id, filepath, filename, mode, page_range, compress_targets)
        return task_id

    elif task_type == "merge":
        filepaths = data.get("filepaths", [])
        filenames = data.get("filenames", [])
        target_kb = data.get("target_kb")
        if target_kb is not None:
            target_kb = float(target_kb)
        if not filepaths:
            raise ValueError("缺少 filepaths")
        display_name = "merge_" + "_".join(filenames[:3]) if filenames else "merge"
        task_params = {"target_kb": target_kb, "filepaths": filepaths,
                       "filenames": filenames} if (target_kb or len(filepaths) > 1) else None
        task_id = create_task(display_name, "merge",
                              input_path=",".join(filepaths),
                              task_params=task_params)
        run_task(task_id, merge_task, task_id, filepaths, filenames, target_kb)
        return task_id

    elif task_type == "batch_ocr":
        filepaths = data.get("filepaths", [])
        filenames = data.get("filenames", [])
        if not filepaths:
            raise ValueError("缺少 filepaths")
        display_name = f"batch_ocr_{len(filepaths)}_files"
        task_params = {"filepaths": filepaths, "filenames": filenames}
        task_id = create_task(display_name, "batch_ocr",
                              input_path=",".join(filepaths),
                              task_params=task_params)
        run_batch_ocr_task(task_id, filepaths, filenames)
        return task_id

    else:
        raise ValueError(f"未知任务类型: {task_type}")
