"""Task 4 · 检查① 位次换算.

核心场景就是大厂翻车的那个：**用错年份的一分一段表算位次**
（实测案例：北京 579 分被判"约 15700 名"，位次前拉约 2440 名 → 推荐必然过高）。
"""
import pytest

from gaokao_audit import config, queries
from gaokao_audit.checks import rank_conversion
from gaokao_audit.models import AuditContext, PlanItem

Y = config.SCORE_YEARS[-1]          # 审计基准年（最新有数据的年份）
CAT = config.CATEGORIES[0]


def _ctx(**kw):
    return AuditContext(year=kw.get("year", Y), category=kw.get("category", CAT))


def _item(seq, score, rank, **kw):
    return PlanItem(
        seq=seq, university_name=kw.get("school", "某大学"), major_group=kw.get("group", "201"),
        claimed_min_score=score, claimed_rank=rank,
        subject_req=kw.get("subject_req"), tier=kw.get("tier", "稳"),
    )


def test_flags_rank_computed_from_another_year(conn):
    """用**另一年**的表算出的位次 → 必须抓到，并且指出是哪一年。"""
    score = 600
    right = queries.rank_of(conn, score, CAT, Y)
    wrong_year = next(y for y in config.SCORE_YEARS if y != Y)
    wrong = queries.rank_of(conn, score, CAT, wrong_year)
    if right is None or wrong is None or right == wrong:
        pytest.skip("这两年该分数位次恰好相同或数据缺失，换个分数段再试")

    out = rank_conversion.check([_item(1, score, wrong)], conn, _ctx())
    kinds = {f.kind for f in out.findings}
    assert "rank_year_mismatch" in kinds
    hit = next(f for f in out.findings if f.kind == "rank_year_mismatch")
    assert str(wrong_year) in hit.detail


def test_consistent_item_yields_no_finding(conn):
    """反例：位次跟本年份的表一致 → 一条都不该报（防误报）。"""
    right = queries.rank_of(conn, 600, CAT, Y)
    if right is None:
        pytest.skip("该分数段不在库里")
    out = rank_conversion.check([_item(1, 600, right)], conn, _ctx())
    assert out.findings == []
    assert out.degraded is None


def test_item_without_claims_is_skipped(conn):
    """条目没写分数或位次 → 不检查、也不报错。"""
    out = rank_conversion.check([_item(1, None, None)], conn, _ctx())
    assert out.findings == [] and out.degraded is None


def test_missing_year_degrades_not_crashes(conn):
    """Review Focus 1：库里没有那一年的表 → 降级，不能崩、也不能瞎报。"""
    out = rank_conversion.check([_item(1, 600, 12345)], conn, _ctx(year=1999))
    assert out.degraded == "insufficient_data"
    assert out.findings == []


def test_deterministic(conn):
    items = [_item(1, 600, 1), _item(2, 610, 2)]
    assert rank_conversion.check(items, conn, _ctx()) == rank_conversion.check(items, conn, _ctx())


def test_out_of_range_score_does_not_discard_other_findings(conn):
    """🔴 回归护栏（评审 C2）：一条分数越出当年一分一段表的范围时，
    只能跳过**这一条**，不能整路降级，更不能把已收集到的其它 finding 一起丢掉。"""
    score = 600
    right = queries.rank_of(conn, score, CAT, Y)
    wrong_year = next(y for y in config.SCORE_YEARS if y != Y)
    wrong = queries.rank_of(conn, score, CAT, wrong_year)
    if right is None or wrong is None or right == wrong:
        pytest.skip("该分数段数据缺失或两年位次相同")

    # 第 2 条的分数（100 分）远低于本科线 —— 超出该年一分一段表的范围
    out = rank_conversion.check([_item(1, score, wrong), _item(2, 100, 1)], conn, _ctx())
    assert out.degraded is None, "一条越界分数不该把整路标成「数据不足」"
    assert any(f.seq == 1 and f.kind == "rank_year_mismatch" for f in out.findings), (
        "越界的那一条把别的 finding 吞掉了"
    )


def test_rank_within_the_same_score_band_is_not_flagged(conn):
    """🔴 回归护栏（make_demo 真跑时踩出来的假阳性）：

    投档表里的「最低位次」是**投档最低排位**，而 rank_of() 给的是**段末位** ——
    同一个分数有几百上千人，两者合法地差出几百名。写死容差 5 会报一堆假阳性。
    容差应按**该分数段的段内人数**给（这是"同分最多差多少"的物理上界）。
    """
    score = 500          # 低分段人多，段内人数大，最能暴露这个问题
    actual = queries.rank_of(conn, score, CAT, Y)
    seg = queries.segment_size(conn, score, CAT, Y)
    if actual is None or not seg or seg < 10:
        pytest.skip("该分数段的段内人数太小，测不出这个问题")

    # 声称的位次落在同一个分数段里（段内第一名的位置）
    claimed = max(1, actual - seg + 1)
    out = rank_conversion.check([_item(1, score, claimed)], conn, _ctx())
    assert out.findings == [], (
        f"同分区间内的位次被误报成错：claimed={claimed} actual={actual} seg={seg}"
    )


def test_across_year_difference_still_flagged_after_tolerance_widening(conn):
    """放宽容差**不能**把真正的错放过去 —— 跨年份的差异是几千名，远超段内人数。"""
    score = 600
    right = queries.rank_of(conn, score, CAT, Y)
    wrong_year = next(y for y in config.SCORE_YEARS if y != Y)
    wrong = queries.rank_of(conn, score, CAT, wrong_year)
    if right is None or wrong is None or right == wrong:
        pytest.skip("数据不足")
    out = rank_conversion.check([_item(1, score, wrong)], conn, _ctx())
    assert out.findings, "放宽容差之后把真正的错放过去了"
