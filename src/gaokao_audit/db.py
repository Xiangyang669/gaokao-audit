"""SQLite 层：表结构与连接。

设计取舍：**`admission_line` 是「专业组」粒度**，由 `major-admission.csv`（专业录取分）
聚合而来 —— 因为只有那张表同时有 `major_group` 与 `min_rank`；`school-admission.csv`
的专业组列在广东的多数年份是空的。

聚合规则（广东按专业组投档，组内最低分即该组投档线）：
    min_score = MIN(组内各专业的录取最低分)
    min_rank  = MAX(组内各专业的录取最低位次)   ← 位次数值越大越靠后
"""
import sqlite3
from pathlib import Path

SCHEMA = """
create table if not exists score_range(
    province        text,
    year            integer,
    category        text,
    batch           text,
    control_score   real,
    score           real,
    cumulative_count integer,
    segment_count   integer,
    rank_range      text
);
create index if not exists ix_score_range on score_range(year, category, score);

create table if not exists admission_line(
    province        text,
    year            integer,
    category        text,
    university_name text,
    major_group     text,
    min_score       real,
    min_rank        integer,
    subject_req     text
);
create index if not exists ix_admission_line on admission_line(year, university_name, major_group);

create table if not exists enrollment_plan(
    province        text,
    year            integer,
    category        text,
    batch           text,
    university_name text,
    major_group     text,
    major_code      text,
    major_name      text,
    subject_req     text,
    plan_count      integer
);
create index if not exists ix_enrollment_plan on enrollment_plan(year, university_name);

create table if not exists rules(key text primary key, value text);
"""


def connect(path: Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """开一个连接。

    ⚠️ **给 FastAPI 用的时候必须 `check_same_thread=False`**：
    同步端点跑在**线程池**里，连接却是在启动线程创建的 —— 不放开这个检查会直接抛
    `ProgrammingError: SQLite objects created in a thread can only be used in that same thread`。
    而这个异常会被 audit.run 吞成 `checker_failed`（降级码留下了、原因没了），
    表现成"四个检查全崩、一条发现都没有"，很难往线程上想。

    ✅ **默认与 sqlite3 一致（严格）**，别为此全局放宽安全网。
    正确的用法是二选一：
      - **生产**：每个请求现开一条（`api/main.py` 的 `conn_factory`）——
        连接在请求线程里创建、也在请求线程里使用，严格检查天然通过；
      - **测试**：复用一条 session 级连接时，显式传 `check_same_thread=False`。
    """
    conn = sqlite3.connect(str(path), check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
