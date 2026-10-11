"""Task 3 · 只读查询层。覆盖 Review Focus 1/2/3/4。"""
import pytest

from gaokao_audit import config, queries

CAT = config.CATEGORIES[0]


def test_missing_year_returns_none(conn):  # Review Focus 1
    assert queries.rank_of(conn, 600, "物理类", 1999) is None


def test_physics_and_history_are_independent(conn):  # Review Focus 3
    a = queries.rank_of(conn, 600, "物理类", 2022)
    b = queries.rank_of(conn, 600, "历史类", 2022)
    assert a is not None and b is not None
    assert a != b, "物理类/历史类位次不可能相同 —— 说明查串了表"


def test_rank_equals_cumulative_at_that_score(conn):  # Review Focus 2
    """位次 = 该分数段的累计人数（段末位），不是上一段的。"""
    year = config.SCORE_YEARS[0]
    row = conn.execute(
        "select cumulative_count from score_range "
        "where score=? and category=? and year=? limit 1",
        (600.0, config.CATEGORIES[0], year),
    ).fetchone()
    if row is None:
        pytest.skip("该分数段不在库里")
    assert queries.rank_of(conn, 600, config.CATEGORIES[0], year) == row[0]


def test_unknown_subject_returns_none(conn):
    assert queries.rank_of(conn, 600, "不存在类", 2022) is None


def test_admission_line_by_group_not_school(conn):  # Review Focus 4
    """同一所学校的**不同专业组**必须能分别取到 —— 取不到就说明按学校名串了。"""
    year = config.ADMISSION_YEARS[0]
    rows = conn.execute(
        "select university_name, major_group from admission_line "
        "where year=? and category=? group by university_name "
        "having count(distinct major_group)>1 limit 1",
        (year, CAT),
    ).fetchone()
    assert rows is not None, "库里没有一所学校有多个专业组 —— 数据有问题"
    school, group = rows[0], rows[1]
    line = queries.admission_line_of(conn, school, group, year, CAT)
    assert line is not None and line.major_group == group

    # 取另一个真实存在的组：返回的行必须标着**被请求的那个组号**。
    # ⚠️ 不要去断言"两个组的分/位次一定不同" —— 两组卡在同一条投档线上是完全合法的。
    # 真正要证明的是"按组过滤"，所以再加一条反向断言：查一个不存在的组号必须拿不到东西。
    others = conn.execute(
        "select major_group from admission_line "
        "where year=? and category=? and university_name=? and major_group<>?",
        (year, CAT, school, group),
    ).fetchall()
    if others:
        other = queries.admission_line_of(conn, school, others[0][0], year, CAT)
        assert other is not None and other.major_group == others[0][0]
    assert queries.admission_line_of(conn, school, "__不存在的组号__", year, CAT) is None


def test_same_group_different_category_returns_the_right_one(conn):
    """🔴 回归护栏（评审 C1）：同校同组，物理类与历史类分数线不同 —— 必须按科类取对。

    实测库里存在这类组合（如 华南师范大学 组 203 / 2022：物理 585/33870 vs 历史 583/3808）。
    漏掉 category 会串表，而且**不报错**，只让结论翻盘。
    """
    row = conn.execute(
        "select university_name, major_group, year from admission_line "
        "group by university_name, major_group, year "
        "having count(distinct category) = 2 and count(distinct min_score) = 2 limit 1"
    ).fetchone()
    if row is None:
        pytest.skip("库里没有跨科类分数线不同的组合，无法验证")
    school, group, year = row

    a = queries.admission_line_of(conn, school, group, year, config.CATEGORIES[0])
    b = queries.admission_line_of(conn, school, group, year, config.CATEGORIES[1])
    assert a is not None and b is not None
    assert a.category == config.CATEGORIES[0] and b.category == config.CATEGORIES[1]
    assert (a.min_score, a.min_rank) != (b.min_score, b.min_rank), (
        "两个科类取到了同一行 —— 说明查询没按科类过滤"
    )


def test_dirty_group_id_is_normalized_on_read(conn):
    """🔴 回归护栏（评审 I1）：全角括号/空格的组号，读的时候也要能命中。

    Plan 2 从截图解析出来的组号必然带这些杂质；不像读时归一化，会静默查不到、不报错。
    """
    row = conn.execute(
        "select university_name, major_group, year, category from admission_line "
        "where major_group is not null limit 1"
    ).fetchone()
    school, group, year, category = row
    for dirty in (f"（{group}）", f"（{group})", f" {group} ", f"({group})"):
        got = queries.admission_line_of(conn, school, dirty, year, category)
        assert got is not None, f"脏组号 {dirty!r} 没被归一化，查不到"


def test_unknown_group_returns_none(conn):
    assert queries.admission_line_of(conn, "不存在的大学", "999", 2022, CAT) is None


def test_rules_roundtrip(conn):
    r = queries.rules_of(conn)
    assert r.province == config.PROVINCE and r.batch == config.BATCH
    assert set(r.categories) == set(config.CATEGORIES)
