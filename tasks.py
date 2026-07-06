"""后台任务执行器 —— 线程池 + subprocess

OCR 任务通过 subprocess 调用 ocr_worker.py 独立进程执行，避免 GIL 阻塞 Flask。
合并、拆分、压缩等轻量任务使用 ThreadPoolExecutor。
"""

import os
import sys
import logging
import subprocess
import traceback
from concurrent.futures import ThreadPoolExecutor

from config import MAX_WORKERS, RESULT_FOLDER, UPLOAD_FOLDER
from models import update_task
from utils.pdf_utils import (
    image_to_pdf,
    merge_pdfs,
    split_pdf_by_mode,
    compress_pdf,
)
from utils.zip_utils import create_zip
from utils.file_utils import get_file_size_kb

logger = logging.getLogger(__name__)

# 轻量任务线程池
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# ocr_worker.py 路径
_OCR_WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocr_worker.py")
_PYTHON_EXE = sys.executable

# 跟踪活跃的 worker 子进程 {task_id: Popen}
_worker_processes: dict[str, subprocess.Popen] = {}


def is_worker_alive(task_id: str) -> bool:
    """检查指定任务的 worker 子进程是否仍在运行"""
    proc = _worker_processes.get(task_id)
    if proc is None:
        return False
    return proc.poll() is None


def _cleanup_worker(task_id: str) -> None:
    """移除已结束的 worker 记录"""
    _worker_processes.pop(task_id, None)


def _update_progress(task_id: str, progress: int, **kwargs) -> None:
    """更新任务进度"""
    update_task(task_id, progress=progress, **kwargs)


def _fail_task(task_id: str, error: str) -> None:
    """标记任务失败"""
    logger.error(f"任务 {task_id} 失败: {error}")
    update_task(task_id, status="failed", error_message=error)


def run_task(task_id: str, func, *args) -> None:
    """在线程池中执行轻量任务"""

    def wrapper():
        try:
            func(*args)
        except Exception as e:
            traceback.print_exc()
            _fail_task(task_id, str(e))

    executor.submit(wrapper)


def _monitor_subprocess(task_id: str, proc: subprocess.Popen) -> None:
    """监控子进程完成状态"""
    def wait_and_check():
        ret = proc.wait()
        _cleanup_worker(task_id)
        if ret != 0:
            from models import get_task
            task = get_task(task_id)
            if task and task["status"] != "failed":
                stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
                _fail_task(task_id, stderr[:500] if stderr else f"OCR worker 异常退出 (code={ret})")
    executor.submit(wait_and_check)


def run_ocr_task(task_id: str, input_path: str, original_filename: str) -> None:
    """通过 subprocess 启动 OCR worker 独立进程"""
    logger.info(f"启动 OCR worker: task_id={task_id}")
    try:
        proc = subprocess.Popen(
            [_PYTHON_EXE, _OCR_WORKER,
             "--task-id", task_id,
             "--mode", "ocr",
             "--input", input_path,
             "--filename", original_filename],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        _worker_processes[task_id] = proc
        _monitor_subprocess(task_id, proc)
    except Exception as e:
        _fail_task(task_id, f"启动 OCR worker 失败: {e}")


def run_batch_ocr_task(task_id: str, input_paths: list[str], file_names: list[str]) -> None:
    """通过 subprocess 启动批量 OCR worker 独立进程"""
    logger.info(f"启动批量 OCR worker: task_id={task_id}, {len(input_paths)} 文件")
    try:
        proc = subprocess.Popen(
            [_PYTHON_EXE, _OCR_WORKER,
             "--task-id", task_id,
             "--mode", "batch_ocr",
             "--input", ",".join(input_paths),
             "--filename", ",".join(file_names)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        _worker_processes[task_id] = proc
        _monitor_subprocess(task_id, proc)
    except Exception as e:
        _fail_task(task_id, f"启动批量 OCR worker 失败: {e}")


# ============ 轻量任务（在线程池执行） ============


def compress_task(task_id: str, input_path: str, original_filename: str, target_kb: float | None) -> None:
    """单文件压缩"""
    _update_progress(task_id, 10)

    base_name = os.path.splitext(original_filename)[0]
    output_path = os.path.join(RESULT_FOLDER, task_id, f"{base_name}_compressed.pdf")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    ext = os.path.splitext(input_path)[1].lower()
    if ext not in (".pdf",):
        pdf_path = os.path.join(RESULT_FOLDER, task_id, f"{base_name}.pdf")
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
        image_to_pdf(input_path, pdf_path)
        input_path = pdf_path

    _update_progress(task_id, 30)

    result_path, actual_kb = compress_pdf(input_path, target_kb, output_path)
    original_kb = get_file_size_kb(input_path)

    logger.info(f"压缩完成: {original_kb:.0f}KB → {actual_kb:.0f}KB (目标: {target_kb}KB)")

    _update_progress(
        task_id, 100, status="completed",
        result_path=result_path,
        result_filename=f"{base_name}_compressed.pdf",
        error_message=(
            f"压缩结果: {actual_kb:.0f}KB (目标: {target_kb}KB)，原始: {original_kb:.0f}KB"
        ) if target_kb else None,
    )


def split_task(
    task_id: str,
    input_path: str,
    original_filename: str,
    mode: str,
    page_range: str | None,
    compress_targets: list[float | None] | None,
) -> None:
    """PDF 拆分提取，可选压缩，结果打包 ZIP"""
    _update_progress(task_id, 10)

    base_name = os.path.splitext(original_filename)[0]
    work_dir = os.path.join(RESULT_FOLDER, task_id)
    os.makedirs(work_dir, exist_ok=True)

    split_dir = os.path.join(work_dir, "split")
    split_files = split_pdf_by_mode(input_path, mode, page_range, split_dir)
    _update_progress(task_id, 50)

    final_files = []
    if compress_targets:
        compress_dir = os.path.join(work_dir, "compressed")
        os.makedirs(compress_dir, exist_ok=True)
        for i, fp in enumerate(split_files):
            target = compress_targets[i] if i < len(compress_targets) else None
            out_path = os.path.join(compress_dir, os.path.basename(fp))
            result_path, _ = compress_pdf(fp, target, out_path)
            final_files.append(result_path)
    else:
        final_files = split_files

    _update_progress(task_id, 80)

    zip_path = os.path.join(work_dir, f"{base_name}_split.zip")
    create_zip(final_files, zip_path)

    _update_progress(
        task_id, 100, status="completed",
        result_path=zip_path,
        result_filename=f"{base_name}_split.zip",
    )


def merge_task(
    task_id: str,
    input_paths: list[str],
    file_names: list[str],
    target_kb: float | None,
) -> None:
    """批量合并（可压缩）"""
    _update_progress(task_id, 10)

    work_dir = os.path.join(RESULT_FOLDER, task_id)
    os.makedirs(work_dir, exist_ok=True)

    pdf_paths = []
    for i, fp in enumerate(input_paths):
        ext = os.path.splitext(fp)[1].lower()
        if ext not in (".pdf",):
            pdf_path = os.path.join(work_dir, f"_convert_{i}.pdf")
            image_to_pdf(fp, pdf_path)
            pdf_paths.append(pdf_path)
        else:
            pdf_paths.append(fp)

    _update_progress(task_id, 30)

    merged_path = os.path.join(work_dir, "merged.pdf")
    merge_pdfs(pdf_paths, merged_path)
    _update_progress(task_id, 60)

    if target_kb:
        compressed_path = os.path.join(work_dir, "merged_compressed.pdf")
        result_path, _ = compress_pdf(merged_path, target_kb, compressed_path)
        result_filename = "merged_compressed.pdf"
    else:
        result_path = merged_path
        result_filename = "merged.pdf"

    _update_progress(
        task_id, 100, status="completed",
        result_path=result_path,
        result_filename=result_filename,
    )
