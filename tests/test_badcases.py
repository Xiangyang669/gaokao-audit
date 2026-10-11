"""Task 8 · 真实 badcase 集.

来源是**公开横评实测里记录的真实错误**，不是我们自己编的题。
它回答一个具体问题：**「真实世界里已经发生过的每一类错，我的系统抓得到吗？」**

⚠️ spec §10.5 纪律②：**必须有一类"已知抓不到"的错误被显式列出来**。
   一版"全部抓到"的评测报告反而不可信。
"""
import json
from pathlib import Path

import pytest

from conftest_helpers import make_ctx, make_items
from eval import inject, run_eval

CASES = Path(__file__).resolve().parents[1] / "eval" / "badcases.json"


def _load():
    return json.loads(CASES.read_text(encoding="utf-8"))


def test_every_badcase_can_be_traced_to_a_source():
    cases = _load()
    assert len(cases) >= 4, "真实 badcase 至少要有 4 条"
    for c in cases:
        assert c.get("source"), f"badcase 缺来源：{c}"
        assert c.get("case"), f"badcase 缺描述：{c}"
        assert "id" in c


def test_no_duplicate_ids():
    ids = [c["id"] for c in _load()]
    assert len(ids) == len(set(ids)), "badcase id 重复"


def test_badcases_run_and_cover_the_mapped_kinds(conn):
    case = inject.Case(items=make_items(conn, n=60), ctx=make_ctx())
    rep = run_eval.run_badcases(conn, case, n_per_kind=50)

    assert 0.0 <= rep.recall <= 1.0
    # 每一条映射到具体检查的 badcase，其对应检查必须真的抓到过东西
    for c in _load():
        k = c.get("expected_finding_kind")
        if k:
            assert k in rep.caught_kinds, f"{c['id']} 对应的检查没抓到任何东西（{k}）"


def test_blind_spots_are_explicitly_listed():
    """抓不到的那类**必须写在报告里**，不能含糊过去。"""
    cases = _load()
    blind = [c for c in cases if not c.get("expected_finding_kind")]
    assert blind, "至少要留一条'已知抓不到'的真实错误 —— 否则这份报告不可信"
    assert all(c.get("why_not_caught") for c in blind), "已知抓不到的条目必须写清原因"
