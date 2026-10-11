"""MCP server：把高考数据的**只读查询**暴露成工具，供别的 agent 挂载。

## 为什么这一层值得单独存在

它把「查数据」从「编排逻辑」里解耦出来，于是它**可以独立被别的 agent 用** ——
任何需要广东高考数据（位次 / 投档线 / 招生计划 / 规则常量）的 agent，
接上这个 server 就行，不需要知道我们这套审计器怎么工作的。

## 🔴 能力边界就是安全边界

**只暴露只读查询，不暴露任何写操作。** 这个 server 是可以被挂到别人家 agent 上的，
所以它能做什么、不能做什么，必须一眼看得出。`tool_names()` 有测试盯着这一点。

## 关于传输

用 **stdio**（本地进程通信）。⚠️ 这也是它相对 A2A 的定位差异：
MCP 管「agent ↔ 工具」（垂直），A2A 管「agent ↔ agent」（水平）。两者不重叠。
"""
from pathlib import Path

from gaokao_audit import config, db, queries
from gaokao_audit.normalize import normalize_group

__all__ = [
    "query_rank",
    "query_admission_line",
    "query_enrollment_plan",
    "query_rules",
    "tool_names",
    "build_server",
]


def _open(db_path: Path | None = None):
    """**每次现开一条**连接 —— 这个坑在本项目已经踩过三次，不再复用。"""
    return db.connect(db_path or config.DB_PATH)


def query_rank(score: int, category: str, year: int) -> int | None:
    """分数 → 全省位次（取该分数段的段末位）。查不到返回 None。"""
    conn = _open()
    try:
        return queries.rank_of(conn, int(score), category, int(year))
    finally:
        conn.close()


def query_admission_line(
    university_name: str, major_group: str, year: int, category: str
) -> dict | None:
    """某校某专业组在某年的投档线。专业组号会自动归一化（全角括号/空格都能吃）。"""
    conn = _open()
    try:
        line = queries.admission_line_of(
            conn, university_name, normalize_group(major_group), int(year), category
        )
        return dict(vars(line)) if line else None
    finally:
        conn.close()


def query_enrollment_plan(
    university_name: str, major_group: str, year: int, category: str
) -> list[dict]:
    """某校某专业组在某年的招生计划（含选科要求）。一组下可能多条专业。"""
    conn = _open()
    try:
        return [
            dict(vars(p))
            for p in queries.enrollment_plan_of(
                conn, university_name, normalize_group(major_group), int(year), category
            )
        ]
    finally:
        conn.close()


def query_rules() -> dict:
    """本数据集覆盖的省份 / 批次 / 科类这些常量。"""
    conn = _open()
    try:
        return dict(vars(queries.rules_of(conn)))
    finally:
        conn.close()


def tool_names() -> list[str]:
    return [n for n in __all__ if n.startswith("query_")]


def build_server():
    """组装成真正的 MCP server（stdio）。工具函数本身是普通函数，便于直测。"""
    from mcp.server import FastMCP

    mcp = FastMCP("gaokao-data")
    for fn in (query_rank, query_admission_line, query_enrollment_plan, query_rules):
        mcp.tool()(fn)
    return mcp


if __name__ == "__main__":  # pragma: no cover
    build_server().run()
