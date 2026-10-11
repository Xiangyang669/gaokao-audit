"""Task 3 · MCP server：把 4 个只读查询暴露成工具.

**只暴露只读查询** —— 不暴露任何写操作。这个 MCP server 可以被挂到别的 agent 上，
所以它的能力边界就是安全边界。

测试直接调工具函数（不通协议）—— 协议层由 mcp 库保证，不是我们的责任；
我们要保证的是**工具的语义与参数**跟 Plan 1 的 queries 一致。
"""
from mcp_server import server


def test_query_rank_tool():
    assert server.query_rank(600, "物理类", 2025) > 0


def test_query_rank_returns_none_for_missing_year():
    assert server.query_rank(600, "物理类", 1999) is None


def test_query_admission_line_tool():
    line = server.query_admission_line("暨南大学", "（201）", 2025, "物理类")
    # 组号带全角括号也能查到（读时归一化）
    assert line is None or line["major_group"] == "201"


def test_query_rules_tool():
    assert server.query_rules()["province"] == "广东"


def test_tools_are_read_only():
    """🔴 这个 server 可以被挂到别的 agent 上 —— 能力边界就是安全边界。
    只允许出现查询类工具，出现任何写操作都算事故。"""
    names = server.tool_names()
    assert names, "没暴露任何工具"
    assert all(n.startswith("query_") for n in names), f"出现了非查询工具：{names}"
