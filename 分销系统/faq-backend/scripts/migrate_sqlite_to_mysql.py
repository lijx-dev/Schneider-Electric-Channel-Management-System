"""Migrate local SQLite data into a MySQL database.

Usage:
    python scripts/migrate_sqlite_to_mysql.py

Optional environment variables:
    SQLITE_PATH       Source sqlite file path. Defaults to ./faq_dev.db
    MYSQL_URL         Target SQLAlchemy/PyMySQL-style URL.
    TRUNCATE_TARGET   true/false. When true, clears target tables before import.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse, unquote

import pymysql
from dotenv import load_dotenv


TABLES_IN_ORDER = [
    "users",
    "questions",
    "daily_quiz_rounds",
    "answer_records",
]


def parse_mysql_url(mysql_url: str) -> dict:
    if not mysql_url.startswith("mysql"):
        raise ValueError("MYSQL_URL 必须是 mysql:// 或 mysql+aiomysql:// 开头")

    normalized = mysql_url.replace("mysql+aiomysql://", "mysql://", 1)
    parsed = urlparse(normalized)

    database = parsed.path.lstrip("/")
    if not database:
        raise ValueError("MYSQL_URL 缺少数据库名")

    return {
        "host": parsed.hostname,
        "port": parsed.port or 3306,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "database": database,
        "charset": "utf8mb4",
        "autocommit": False,
    }


def sqlite_connect(sqlite_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(sqlite_path))
    connection.row_factory = sqlite3.Row
    return connection


def mysql_connect(mysql_url: str):
    return pymysql.connect(**parse_mysql_url(mysql_url))


def fetch_table_rows(connection: sqlite3.Connection, table_name: str) -> tuple[list[str], list[tuple]]:
    cursor = connection.execute(f"SELECT * FROM {table_name}")
    columns = [item[0] for item in cursor.description]
    rows = []
    for row in cursor.fetchall():
        values = []
        for column in columns:
            value = row[column]
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            values.append(value)
        rows.append(tuple(values))
    return columns, rows


def count_rows(connection, table_name: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        return int(cursor.fetchone()[0])


def truncate_target_tables(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        for table_name in reversed(TABLES_IN_ORDER):
            cursor.execute(f"TRUNCATE TABLE {table_name}")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    connection.commit()


def insert_rows(connection, table_name: str, columns: Iterable[str], rows: list[tuple]) -> int:
    if not rows:
        return 0

    columns = list(columns)
    col_clause = ", ".join(f"`{column}`" for column in columns)
    placeholder_clause = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO `{table_name}` ({col_clause}) VALUES ({placeholder_clause})"

    with connection.cursor() as cursor:
        cursor.executemany(sql, rows)
    return len(rows)


def filter_orphan_rows(
    table_name: str,
    columns: list[str],
    rows: list[tuple],
    valid_user_ids: set[str],
    valid_question_ids: set[int],
) -> tuple[list[tuple], int]:
    if table_name != "answer_records":
        return rows, 0

    user_idx = columns.index("user_id")
    question_idx = columns.index("question_id")

    filtered_rows: list[tuple] = []
    skipped = 0
    for row in rows:
        user_id = row[user_idx]
        question_id = row[question_idx]
        if user_id not in valid_user_ids or question_id not in valid_question_ids:
            skipped += 1
            continue
        filtered_rows.append(row)

    return filtered_rows, skipped


def main() -> None:
    load_dotenv()

    project_root = Path(__file__).resolve().parents[1]
    sqlite_path = Path(os.getenv("SQLITE_PATH", project_root / "faq_dev.db"))
    mysql_url = os.getenv("MYSQL_URL") or os.getenv("DATABASE_URL")
    truncate_target = os.getenv("TRUNCATE_TARGET", "false").strip().lower() == "true"

    if not sqlite_path.exists():
        raise FileNotFoundError(f"找不到 SQLite 文件: {sqlite_path}")

    if not mysql_url:
        raise RuntimeError("请设置 MYSQL_URL 或 DATABASE_URL")

    print(f"[1/4] 读取源库: {sqlite_path}")
    print(f"[2/4] 连接目标库: {parse_mysql_url(mysql_url)['database']}")

    with closing(sqlite_connect(sqlite_path)) as sqlite_conn, closing(mysql_connect(mysql_url)) as mysql_conn:
        if truncate_target:
            print("清空目标表中...")
            truncate_target_tables(mysql_conn)

        migrated_counts: dict[str, int] = {}
        skipped_counts: dict[str, int] = {}
        user_columns, user_rows = fetch_table_rows(sqlite_conn, "users")
        question_columns, question_rows = fetch_table_rows(sqlite_conn, "questions")
        valid_user_ids = {row[user_columns.index("id")] for row in user_rows}
        valid_question_ids = {row[question_columns.index("id")] for row in question_rows}

        for table_name in TABLES_IN_ORDER:
            columns, rows = fetch_table_rows(sqlite_conn, table_name)
            rows, skipped = filter_orphan_rows(
                table_name,
                columns,
                rows,
                valid_user_ids=valid_user_ids,
                valid_question_ids=valid_question_ids,
            )
            inserted = insert_rows(mysql_conn, table_name, columns, rows)
            migrated_counts[table_name] = inserted
            skipped_counts[table_name] = skipped
            print(f"已迁移 {table_name}: {inserted} 条")
            if skipped:
                print(f"跳过 {table_name} 孤儿记录: {skipped} 条")

        mysql_conn.commit()
        print("[3/4] 迁移完成，开始校验数量...")

        for table_name in TABLES_IN_ORDER:
            source_count = len(fetch_table_rows(sqlite_conn, table_name)[1]) - skipped_counts.get(table_name, 0)
            target_count = count_rows(mysql_conn, table_name)
            print(f"{table_name}: sqlite={source_count}, mysql={target_count}")
            if source_count != target_count:
                raise RuntimeError(f"表 {table_name} 数量不一致，迁移终止")

        print("[4/4] 校验通过，迁移成功。")


if __name__ == "__main__":
    main()
