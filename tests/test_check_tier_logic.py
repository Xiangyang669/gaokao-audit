"""Task 5 · 检查③ 分档逻辑（冲/稳/保 是否自洽）.

要抓的失败模式（实测案例）：**把"位次比最低位次还靠后"的专业放进"稳"档** ——
考生 18140 位，该组最低 17506 位。位次数值越大越靠后，所以 18140 > 17506 ⇒ 根本够不着，
却标成"稳"，这就是自相矛盾。
"""
from gaokao_audit import config
from gaokao_audit.checks import tier_logic as chk
from gaokao_audit.models import AuditContext, PlanItem

Y = config.ADMISSION_YEARS[0]
CAT = config.CATEGORIES[0]


def _rows(conn, n=1):
    return conn.execute(
        "select university_name, major_group, min_rank from admission_line "
        "where year=? and category=? and min_rank is not null order by min_rank limit ?",
        (Y, CAT, n),
    ).fetchall()


def _item(seq, school, group, tier):
    return PlanItem(seq=seq, university_name=school, major_group=group,
                    claimed_min_score=None, claimed_rank=None,
                    subject_req=None, tier=tier)


def _ctx(candidate_rank):
    return AuditContext(year=Y, category=CAT, candidate_rank=candidate_rank)


def test_safe_tier_that_is_actually_out_of_reach_is_flagged(conn):
    school, group, min_rank = _rows(conn)[0]
    # 考生位次比该组最低位次**更靠后**（数值更大）⇒ 够不着，却标"稳"
    out = chk.check([_item(1, school, group, "稳")], conn, _ctx(int(min_rank) + 500))
    assert [f.kind for f in out.findings] == ["tier_inconsistent"]
    assert out.findings[0].claimed == "稳"


def test_safe_tier_within_reach_is_not_flagged(conn):
    school, group, min_rank = _rows(conn)[0]
    out = chk.check([_item(1, school, group, "稳")], conn, _ctx(int(min_rank) - 500))
    assert out.findings == []


def test_reach_tier_out_of_reach_is_not_flagged(conn):
    """标"冲"本来就允许够不着 —— 不该报。"""
    school, group, min_rank = _rows(conn)[0]
    out = chk.check([_item(1, school, group, "冲")], conn, _ctx(int(min_rank) + 500))
    assert out.findings == []


def test_without_candidate_rank_is_skipped(conn):
    school, group, _ = _rows(conn)[0]
    out = chk.check([_item(1, school, group, "稳")], conn, AuditContext(year=Y, category=CAT))
    assert out.findings == [] and out.degraded is None


def test_group_not_in_db_is_skipped(conn):
    out = chk.check([_item(1, "不存在的大学", "999", "稳")], conn, _ctx(10000))
    assert out.findings == []
