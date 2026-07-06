"""应用配置文件"""

import os
import tempfile

# Flask 基础配置
SECRET_KEY = os.environ.get("SECRET_KEY", "pdf-tool-dev-key--change-in-production")
MAX_CONTENT_LENGTH = 1 * 1024 * 1024 * 1024  # 1GB 上传限制

# 上传与结果存储目录
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
RESULT_FOLDER = os.path.join(BASE_DIR, "results")
TEMP_FOLDER = os.path.join(tempfile.gettempdir(), "pdf_tool")

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "bmp", "tiff", "tif"}

# 批量处理限制
MAX_BATCH_FILES = 10

# 线程池配置
MAX_WORKERS = 3  # 并发处理任务数

# OCR 配置
OCR_DPI = 200
OCR_LANG = "ch"

# Poppler 路径（Windows 需指定 bin 目录，可通过环境变量覆盖）
POPPLER_PATH = os.environ.get("POPPLER_PATH", "")

# 结果文件保留时间（秒），默认 24 小时
RESULT_RETENTION_SECONDS = 24 * 60 * 60

# 数据库路径
DATABASE = os.path.join(BASE_DIR, "tasks.db")
