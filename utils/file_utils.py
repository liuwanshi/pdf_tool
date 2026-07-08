"""文件验证、清理等工具函数

提供上传文件的安全过滤、格式校验、保存、大小计算及过期清理。
"""

import os
import re
import uuid

from werkzeug.datastructures import FileStorage

from config import ALLOWED_EXTENSIONS, MAX_BATCH_FILES


def sanitize_filename(filename: str) -> str:
    """安全化文件名：去除危险字符但保留中文等 Unicode 字符

    处理流程：
    1. 替换路径分隔符（/ 和 \\）为下划线，防止目录穿越攻击
    2. 剔除 Windows 文件名非法字符（ASCII 控制字符 + :*?"<>|）
    3. 去除首尾空格和点（Windows 不允许以空格或点结尾）
    4. 若清洗后文件名已空，生成随机 UUID 作为兜底
    """
    # 替换路径分隔符为下划线，防止 ../../etc/passwd 这类攻击
    filename = filename.replace("/", "_").replace("\\", "_")
    # 剔除 ASCII 控制字符(0x00-0x1f) 和 Windows 文件名非法字符 :*?"<>|
    filename = re.sub(r'[\x00-\x1f:*?"<>|]', "", filename)
    # 去除首尾空格和点
    filename = filename.strip(" .")
    # 兜底：文件名完全由非法字符组成时，生成随机名
    if not filename or filename.startswith("."):
        base, ext = os.path.splitext(filename)
        if not base:
            filename = f"{uuid.uuid4().hex[:8]}{ext}"
    return filename


def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否在白名单内

    白名单定义在 config.ALLOWED_EXTENSIONS，
    包含 pdf, png, jpg, jpeg, bmp, tiff, tif。
    """
    # 无扩展名的文件直接拒绝
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def validate_file(file: FileStorage) -> str | None:
    """验证单个上传文件，返回错误信息或 None（通过）

    检查流程：
    1. 文件对象是否为空
    2. 文件扩展名是否在白名单内
    任一不通过 → 返回中文错误提示
    """
    # 检查1：文件对象不存在或文件名为空
    if not file or not file.filename:
        return "未选择文件"

    # 检查2：扩展名不在白名单内
    if not allowed_file(file.filename):
        ext = file.filename.rsplit(".", 1)[1].lower() if "." in file.filename else "未知"
        return f"不支持的文件格式: .{ext}，仅支持: {', '.join(sorted(ALLOWED_EXTENSIONS))}"

    return None


def validate_batch_files(files: list[FileStorage]) -> str | None:
    """验证批量上传文件列表，返回错误信息或 None

    检查流程：
    1. 文件列表是否为空（全部未选）
    2. 有效文件数量是否超过上限（config.MAX_BATCH_FILES，默认 10）
    3. 逐一检查每个文件扩展名是否合法
    """
    # 检查1：全部未选择
    if not files or all(not f or not f.filename for f in files):
        return "未选择文件"

    # 检查2：数量上限
    valid_files = [f for f in files if f and f.filename]
    if len(valid_files) > MAX_BATCH_FILES:
        return f"批量上传最多 {MAX_BATCH_FILES} 个文件，当前 {len(valid_files)} 个"

    # 检查3：逐个验证格式
    for f in valid_files:
        error = validate_file(f)
        if error:
            return error

    return None


def save_upload(file: FileStorage, upload_folder: str) -> str:
    """保存上传文件，返回保存后的绝对路径

    文件名先经过 sanitize_filename() 安全清洗，
    若目标路径已存在同名文件，自动追加序号避免覆盖。
    重名策略：原文件名.pdf → 原文件名_1.pdf → 原文件名_2.pdf ...
    """
    filename = sanitize_filename(file.filename)
    filepath = os.path.join(upload_folder, filename)
    # 处理重名：遇到同名文件递增序号（base_1.ext, base_2.ext ...）
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
