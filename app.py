"""Flask 应用入口"""

import os
import logging
from logging.handlers import RotatingFileHandler

from flask import Flask

from config import (
    SECRET_KEY, UPLOAD_FOLDER, RESULT_FOLDER, DATABASE,
    LOG_LEVEL, LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT,
)
from models import init_db, mark_interrupted_tasks, mark_stale_tasks


def _setup_logging() -> None:
    """配置日志：控制台 + 可选文件输出（支持滚动）"""
    handlers = [logging.StreamHandler()]

    if LOG_FILE:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        handlers.append(file_handler)

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """创建并配置 Flask 应用"""
    _setup_logging()

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

    logger.info(f"线程池大小: {os.environ.get('MAX_WORKERS', 3)}")
    logger.info(f"日志级别: {LOG_LEVEL}")

    return app


app = create_app()

if __name__ == "__main__":
    logger.info("服务启动: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
