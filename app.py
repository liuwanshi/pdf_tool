"""Flask 应用入口"""

import os
import sys
import logging

# 确保 stdout/stderr 使用 UTF-8（避免 Windows GBK 与终端 UTF-8 不一致导致的乱码）
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from flask import Flask

from config import SECRET_KEY, UPLOAD_FOLDER, RESULT_FOLDER, DATABASE
from models import init_db, mark_interrupted_tasks, mark_stale_tasks

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """创建并配置 Flask 应用"""
    app = Flask(__name__)
    app.secret_key = SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024 * 1024  # 1GB

    # 确保必要目录存在
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(RESULT_FOLDER, exist_ok=True)

    # 初始化数据库
    init_db()
    logger.info(f"数据库初始化完成: {DATABASE}")

    # 标记上次异常中断的任务
    interrupted = mark_interrupted_tasks()
    stale = mark_stale_tasks()
    if interrupted or stale:
        logger.info(f"中断任务清理: {interrupted} 个重启中断, {stale} 个超时")

    # 注册路由
    from routes import register_routes
    register_routes(app)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
