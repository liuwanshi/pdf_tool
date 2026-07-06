"""文件验证、清理等工具函数"""

import os
import re
import uuid

from werkzeug.datastructures import FileStorage

from config import ALLOWED_EXTENSIONS, MAX_BATCH_FILES


def sanitize_filename(filename: str) -> str:
    """安全化文件名：去除危险字符但保留中文等 Unicode 字符"""
    # 移除路径分隔符和危险字符
    filename = filename.replace("/", "_").replace("\\", "_")
    # 移除 Windows 非法字符
    filename = re.sub(r'[\x00-\x1f:*?"<>|]', "", filename)
    # 去除首尾空格和点
    filename = filename.strip(" .")
    # 如果文件名被清空（全部是非法字符），生成一个随机名
    if not filename or filename.startswith("."):
        base, ext = os.path.splitext(filename)
        if not base:
            filename = f"{uuid.uuid4().hex[:8]}{ext}"
    return filename


def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否在白名单内"""
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def validate_file(file: FileStorage) -> str | None:
    """验证单个上传文件，返回错误信息或 None（通过）"""
    if not file or not file.filename:
        return "未选择文件"

    if not allowed_file(file.filename):
        ext = file.filename.rsplit(".", 1)[1].lower() if "." in file.filename else "未知"
        return f"不支持的文件格式: .{ext}，仅支持: {', '.join(sorted(ALLOWED_EXTENSIONS))}"

    return None


def validate_batch_files(files: list[FileStorage]) -> str | None:
    """验证批量上传文件列表，返回错误信息或 None"""
    if not files or all(not f or not f.filename for f in files):
        return "未选择文件"

    valid_files = [f for f in files if f and f.filename]
    if len(valid_files) > MAX_BATCH_FILES:
        return f"批量上传最多 {MAX_BATCH_FILES} 个文件，当前 {len(valid_files)} 个"

    for f in valid_files:
        error = validate_file(f)
        if error:
            return error

    return None


def save_upload(file: FileStorage, upload_folder: str) -> str:
    """保存上传文件，返回保存后的绝对路径"""
    filename = sanitize_filename(file.filename)
    filepath = os.path.join(upload_folder, filename)
    # 处理重名
    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(filepath):
        new_name = f"{base}_{counter}{ext}"
        filepath = os.path.join(upload_folder, new_name)
        counter += 1
    file.save(filepath)
    return filepath


def get_file_size_kb(filepath: str) -> float:
    """获取文件大小（KB）"""
    return os.path.getsize(filepath) / 1024


def cleanup_old_files(folder: str, max_age_seconds: int) -> int:
    """清理超过指定时间的文件，返回删除的文件数"""
    import time

    if not os.path.isdir(folder):
        return 0

    now = time.time()
    deleted = 0
    for filename in os.listdir(folder):
        filepath = os.path.join(folder, filename)
        if os.path.isfile(filepath):
            if now - os.path.getmtime(filepath) > max_age_seconds:
                try:
                    os.remove(filepath)
                    deleted += 1
                except OSError:
                    pass
    return deleted
