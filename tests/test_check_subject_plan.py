"""Task 5 · 检查④ 选科能不能报.

⚠️ 真实数据有两种 `subject_req` 格式（2022/2024 带"首选X，再选Y"；2025 只列再选科目），
两种都要覆盖 —— 只认一种会让另一年的检查**静默失效**。
"""
import pytest

from gaokao_audit import config
from gaokao_audit.checks import subject_plan as chk
from gaokao_audit.models import AuditContext, PlanItem


def _req_row(conn, year):
    """找一个**有专业组号**的选科要求样本。

    ⚠️ enrollment_plan 的 major_group 只有 2025 非空（2022/2024 全空）——
    而检查④必须按专业组查，所以它实际只在 2025 可用。这个 helper 会把这条边界暴露出来，
    而不是假装所有年份都能查。
    """
    return conn.execute(
        "select university_name, major_group, subject_req from enrollment_plan "
        "where year=? and subject_req is not null and major_group is not null "
        "and subject_req not like '%不限%' order by subject_req limit 1",
        (year,),
    ).fetchone()


def _subjects_that_cannot_satisfy(req: str) -> tuple[str, ...]:
    """挑三个与该要求完全不重叠的科目 —— 保证必然不满足。"""
    return tuple(s for s in ("物理", "化学", "生物", "政治", "地理", "历史") if s not in req)[:3]


def _item(seq, school, group):
    return PlanItem(seq=seq, university_name=school, major_group=group,
                    claimed_min_score=None, claimed_rank=None,
                    subject_req=None, tier="稳")


def _ctx(year, subjects):
    return AuditContext(year=year, category=config.CATEGORIES[0], candidate_subjects=subjects)


# ── 解析器单元测试（两种格式 + 或语义）──

@pytest.mark.parametrize("req,subjects,expected", [
    ("首选物理，再选化学", ("物理", "化学", "生物"), True),
    ("首选物理，再选化学", ("历史", "政治", "地理"), False),
    ("首选物理，再选不限", ("物理", "地理", "政治"), True),
    ("化学", ("物理", "化学", "生物"), True),            # 2025 格式
    ("化学", ("物理", "生物", "地理"), False),           # 2025 格式
    ("化学和生物", ("物理", "化学", "生物"), True),
    ("化学和生物", ("物理", "化学", "地理"), False),
    ("化学/生物(2选1)", ("物理", "生物", "地理"), True),  # 或：命中其一即可
    ("化学/生物(2选1)", ("物理", "地理", "政治"), False),
    ("不限", ("历史", "政治", "地理"), True),
])
def test_parser(req, subjects, expected):
    assert chk.satisfied(req, subjects) is expected


# ── 检查行为（用真实数据）──

def test_ineligible_subjects_are_flagged(conn):
    row = _req_row(conn, 2025)  # 只有 2025 有专业组号
    school, group, req = row
    out = chk.check([_item(1, school, group)], conn, _ctx(2025, _subjects_that_cannot_satisfy(req)))
    assert [f.kind for f in out.findings] == ["subject_not_allowed"]
    assert req in out.findings[0].evidence


def test_2025_format_is_checked_not_silently_passed(conn):
    """🔴 回归护栏：2025 的格式若被当成"无法解析"，这个检查会永远报不出问题。"""
    row = _req_row(conn, 2025)
    assert row is not None, "2025 没有可用的选科要求样本"
    school, group, req = row
    out = chk.check([_item(1, school, group)], conn, _ctx(2025, ("历史", "政治", "地理")))
    assert [f.kind for f in out.findings] == ["subject_not_allowed"], (
        f"2025 格式「{req}」没被检查 —— 解析器可能又只认 2022 的格式"
    )


def test_no_candidate_subjects_is_skipped(conn):
    row = _req_row(conn, 2025)
    out = chk.check([_item(1, row[0], row[1])], conn, _ctx(2025, ()))
    assert out.findings == [] and out.degraded is None


def test_group_without_requirement_is_skipped(conn):
    out = chk.check([_item(1, "不存在的大学", "999")], conn, _ctx(2025, ("历史",)))
    assert out.findings == []
