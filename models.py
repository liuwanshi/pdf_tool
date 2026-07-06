"""SQLite 任务模型 —— 数据库操作函数"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from config import DATABASE

logger = logging.getLogger(__name__)


def get_db() -> sqlite3.Connection:
    """获取数据库连接（WAL 模式 + busy_timeout 保证多进程并发安全）"""
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    """初始化数据库表（含向后兼容的字段迁移）"""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                original_filename TEXT NOT NULL,
                task_type TEXT NOT NULL,
                progress INTEGER DEFAULT 0,
                status TEXT DEFAULT 'processing',
                error_message TEXT,
                result_path TEXT,
                result_filename TEXT,
                input_path TEXT,
                task_params TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 向后兼容：旧表可能缺少 input_path、task_params 字段
        _migrate_add_column(conn, "tasks", "input_path", "TEXT")
        _migrate_add_column(conn, "tasks", "task_params", "TEXT")
        conn.commit()


def _migrate_add_column(conn: sqlite3.Connection, table: str, column: str, col_type: str) -> None:
    """安全添加列：如果列已存在则跳过"""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        logger.info(f"数据库迁移: {table}.{column} 已添加")
    except sqlite3.OperationalError:
        pass  # 列已存在


def create_task(original_filename: str, task_type: str,
                input_path: str = "", task_params: dict | None = None) -> str:
    """创建任务记录，返回任务 ID"""
    task_id = str(uuid.uuid4())
    params_json = json.dumps(task_params, ensure_ascii=False) if task_params else None
    with get_db() as conn:
        conn.execute(
            "INSERT INTO tasks (id, original_filename, task_type, input_path, task_params) "
            "VALUES (?, ?, ?, ?, ?)",
            (task_id, original_filename, task_type, input_path, params_json),
        )
        conn.commit()
    return task_id


def update_task(task_id: str, **kwargs: Any) -> None:
    """更新任务字段"""
    allowed = {"progress", "status", "error_message", "result_path",
               "result_filename", "input_path"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values())
    values.append(task_id)
    with get_db() as conn:
        conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
        conn.commit()


def get_task(task_id: str) -> dict | None:
    """获取单个任务"""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        return None
    return dict(row)


def get_all_tasks() -> list[dict]:
    """获取所有任务（按创建时间倒序）"""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def mark_interrupted_tasks() -> int:
    """启动时将所有 processing 任务标记为 interrupted，返回标记数量"""
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE tasks SET status = 'interrupted', "
            "error_message = '服务器重启，任务中断' "
            "WHERE status = 'processing'"
        )
        conn.commit()
        count = cursor.rowcount
        if count > 0:
            logger.info(f"已标记 {count} 个中断任务")
        return count


def mark_stale_tasks(timeout_minutes: int = 30) -> int:
    """将超时的 processing 任务标记为 interrupted（防止 worker 静默崩溃）"""
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE tasks SET status = 'interrupted', "
            "error_message = '任务超时（可能 worker 崩溃）' "
            "WHERE status = 'processing' "
            "AND datetime(created_at, ?) < datetime('now', 'localtime')",
            (f"+{timeout_minutes} minutes",)
        )
        conn.commit()
        count = cursor.rowcount
        if count > 0:
            logger.warning(f"已标记 {count} 个超时任务")
        return count
