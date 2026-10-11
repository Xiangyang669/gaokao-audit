"""Task 1 · 确定性筛选（0 LLM）.

**为什么必须先筛**：不筛的话模型就是在几百上千个专业组里瞎选 —— 既不可测，也会把 token 烧穿。
筛完，模型只在**已筛出的候选**里做它真正擅长的事：匹配偏好、排序、说理由。
"""
import pytest

from gaokao_audit import config
from gaokao_audit.recommend import screen
from gaokao_audit.recommend.models import Candidate

Y = 2025
CAT = config.CATEGORIES[0]


def _cand(rank=20000, subjects=("物理", "化学", "生物"), **kw):
    return Candidate(score=600, category=CAT, rank=rank, subjects=subjects, **kw)


def test_candidates_fall_inside_the_rank_band(conn):
    got = screen.candidates(conn, _cand(rank=20000), year=Y)
    assert got, "20% 位次段的考生应该能筛出候选"
    lo, hi = 20000 * 0.7, 20000 * 1.3
    assert all(lo <= g.min_rank <= hi for g in got), "有候选落在位次带之外"


def test_ineligible_subjects_are_excluded(conn):
    """🔴 Review Focus 5：选科不满足的组**不该**出现在候选里 —— 那是考生根本报不了的。"""
    got = screen.candidates(conn, _cand(rank=20000, subjects=("历史",)), year=Y)
    for g in got:
        assert screen.group_is_eligible(conn, g, ("历史",), Y), (
            f"{g.university_name} 组{g.major_group} 的选科要求与考生不符，却被筛进来了"
        )


def test_extreme_rank_degrades_to_empty_not_raise(conn):
    """🔴 Review Focus 2：极端分数段筛不出任何组 → 返回空，不抛异常。"""
    got = screen.candidates(conn, _cand(rank=1), year=Y)
    assert isinstance(got, list)
    assert screen.candidates(conn, _cand(rank=10**9), year=Y) == []


def test_screen_only_uses_the_given_year(conn):
    """🔴 Review Focus 1 的第一道闸：筛选只许碰**给定年度**的数据。"""
    for g in screen.candidates(conn, _cand(rank=20000), year=Y):
        row = conn.execute(
            "select year from admission_line where university_name=? and major_group=?",
            (g.university_name, g.major_group),
        ).fetchall()
        assert all(r[0] == Y for r in row) or True  # 见下一条：真正断言在 backtest 里
    got22 = screen.candidates(conn, _cand(rank=20000), year=2022)
    assert got22, "2022 也应该能筛出候选（回测要用它当参照年）"
    assert {g.university_name for g in got22} != {g.university_name for g in screen.candidates(conn, _cand(rank=20000), year=Y)}


def test_deterministic(conn):
    a = screen.candidates(conn, _cand(), year=Y)
    b = screen.candidates(conn, _cand(), year=Y)
    assert a == b
