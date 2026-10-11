"""Task 5 · 检查② 投档线核对.

要抓的失败模式：**表里声称的投档线跟真实值对不上**
（实测案例：把首医 2025 北京最低分写成 582，官方是 548）。
"""
from gaokao_audit import config
from gaokao_audit.checks import admission_line as chk
from gaokao_audit.models import AuditContext, PlanItem

Y = config.ADMISSION_YEARS[0]


def _ctx():
    return AuditContext(year=Y, category=config.CATEGORIES[0])


def _real_row(conn):
    return conn.execute(
        "select university_name, major_group, min_score from admission_line "
        "where year=? and category=? and min_score is not null limit 1",
        (Y, config.CATEGORIES[0]),
    ).fetchone()


def _item(seq, school, group, score):
    return PlanItem(seq=seq, university_name=school, major_group=group,
                    claimed_min_score=score, claimed_rank=None,
                    subject_req=None, tier="稳")


def test_wrong_score_is_flagged(conn):
    school, group, real = _real_row(conn)
    out = chk.check([_item(1, school, group, int(real) - 30)], conn, _ctx())
    assert [f.kind for f in out.findings] == ["line_mismatch"]
    f = out.findings[0]
    assert f.claimed == int(real) - 30 and f.actual == real
    assert school in f.evidence


def test_correct_score_is_not_flagged(conn):
    school, group, real = _real_row(conn)
    out = chk.check([_item(1, school, group, int(real))], conn, _ctx())
    assert out.findings == []


def test_group_not_in_db_is_skipped_not_flagged(conn):
    """一个组在某年不招生是正常的 —— 跳过，不要报成"抄错了"。"""
    out = chk.check([_item(1, "不存在的大学", "999", 600)], conn, _ctx())
    assert out.findings == [] and out.degraded is None


def test_no_score_claim_is_skipped(conn):
    school, group, _ = _real_row(conn)
    out = chk.check([_item(1, school, group, None)], conn, _ctx())
    assert out.findings == []


def test_missing_year_degrades(conn):
    out = chk.check([_item(1, "某大学", "201", 600)], conn, AuditContext(year=1999, category=config.CATEGORIES[0]))
    assert out.degraded == "insufficient_data"
