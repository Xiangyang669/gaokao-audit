"""Task 7 · 评测 harness：把注入跑一遍，量出检出率 / 误报率.

⚠️ spec §10.5 纪律①：**样本量第一天就要够**（≥50 × 4 类）。
   项目① 栽在"18 道题撑不起结论"，这里不重蹈。
"""
import pytest

from conftest_helpers import make_ctx, make_items
from eval import inject, run_eval

KINDS = ("year", "number", "tier", "subject")


@pytest.fixture
def case(conn):
    return inject.Case(items=make_items(conn, n=60), ctx=make_ctx())


def test_report_shape(conn, case):
    rep = run_eval.run(case, conn, n_per_kind=50)
    assert 0.0 <= rep.recall <= 1.0
    assert 0.0 <= rep.precision <= 1.0
    assert set(rep.per_kind) == set(KINDS)
    assert isinstance(rep.missed_kinds, list)


def test_sample_size_floor_is_enforced(conn, case):
    """样本量低于门槛必须报出来，而不是悄悄给个数。"""
    rep = run_eval.run(case, conn, n_per_kind=5)
    assert rep.warnings, "样本量不足时必须有告警"


def test_clean_case_has_few_false_positives(conn, case):
    """干净的表（没注入）跑一遍，误报应当很低 —— 否则说明检查太敏感。"""
    rep = run_eval.run(inject.Case(items=case.items, ctx=case.ctx), conn, n_per_kind=50)
    assert rep.baseline_findings is not None
    assert rep.baseline_findings <= max(2, len(case.items) // 5), (
        f"干净表报出 {rep.baseline_findings} 条问题 —— 误报太高，检查有问题"
    )


def test_missed_kinds_are_explicitly_listed(conn, case):
    """spec §10.5 纪律②：抓不到的那类必须**显式列出来**，不能并进总数糊过去。"""
    rep = run_eval.run(case, conn, n_per_kind=50)
    for kind in rep.missed_kinds:
        assert rep.per_kind[kind] == 0.0, "missed_kinds 里只能放检出率为 0 的类别"
