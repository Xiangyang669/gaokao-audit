"""Task 6 · 编排：把四路检查跑完并汇总.

两条硬要求：
  ① 一路崩了不能拖垮其余（且要如实记下哪一路崩了）
  ② 输出必须**确定性**（同样的输入两次跑，逐条一致）
"""
import pytest

from gaokao_audit import audit, config, queries
from gaokao_audit.models import AuditContext, PlanItem

Y = 2025  # 2025 数据最全（专业组、选科要求都在），编排测试统一用它
CAT = config.CATEGORIES[0]


@pytest.fixture
def sample_items(conn):
    rows = conn.execute(
        "select university_name, major_group, min_score from admission_line "
        "where year=? and min_score is not null limit 3",
        (Y,),
    ).fetchall()
    items = []
    for i, (school, group, score) in enumerate(rows, start=1):
        rank = queries.rank_of(conn, int(score), CAT, Y)
        items.append(
            PlanItem(
                seq=i, university_name=school, major_group=group,
                claimed_min_score=int(score), claimed_rank=rank,
                subject_req=None, tier="稳",
            )
        )
    assert items, "没有可用样本"
    return items


@pytest.fixture
def ctx():
    return AuditContext(
        year=Y, category=CAT, candidate_rank=999999, candidate_subjects=("物理", "化学", "生物")
    )


def test_runs_all_four_checks(conn, sample_items, ctx):
    r = audit.run(sample_items, conn, ctx)
    assert {o.name for o in r.outcomes} == {
        "rank_conversion", "admission_line", "tier_logic", "subject_plan"
    }


def test_one_checker_crash_does_not_block_others(conn, sample_items, ctx, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr("gaokao_audit.checks.rank_conversion.check", boom)
    r = audit.run(sample_items, conn, ctx)

    assert len(r.outcomes) == 3, "一路崩了，其余三路必须照跑"
    assert r.degraded["rank_conversion"].startswith("checker_failed")
    assert {o.name for o in r.outcomes} == {"admission_line", "tier_logic", "subject_plan"}


def test_check_declared_degradation_is_surfaced(conn, sample_items):
    """检查自己报的 degraded 也要汇总上来（崩溃与否是两回事）。"""
    r = audit.run(sample_items, conn, AuditContext(year=1999, category=CAT))
    assert r.degraded, "基准年没数据，至少要有检查报 degraded"


def test_findings_are_sorted_and_deterministic(conn, sample_items, ctx):
    a = audit.run(sample_items, conn, ctx)
    b = audit.run(sample_items, conn, ctx)
    assert a == b
    keys = [(f.seq, f.kind) for f in a.findings]
    assert keys == sorted(keys), "findings 必须按 (seq, kind) 排序，否则输出不可复现"


def test_intentionally_broken_item_is_reported(conn, sample_items, ctx):
    """真喂一条坏数据进去，确认编排真的把问题带出来了。"""
    bad = sample_items[0]
    wrong = PlanItem(
        seq=bad.seq, university_name=bad.university_name, major_group=bad.major_group,
        claimed_min_score=bad.claimed_min_score,
        claimed_rank=(bad.claimed_rank or 0) + 9999,   # 位次明显错
        subject_req=None, tier="稳",
    )
    r = audit.run([wrong], conn, ctx)
    assert any(f.kind in ("rank_mismatch", "rank_year_mismatch") for f in r.findings)
