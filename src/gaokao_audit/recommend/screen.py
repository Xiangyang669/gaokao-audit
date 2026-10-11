"""① 确定性筛选（**0 LLM**）。

把候选缩到考生位次附近的一个**带**里 —— 不筛的话模型要在几百上千个专业组里瞎选，
既不可测、也把 token 烧穿。**筛完，模型只做它真正擅长的事：匹配偏好、排序、说理由。**

⚠️ **只碰 `year` 这一年的数据。** 回测会给一个参照年（2022），
那时绝不能看到检验年（2025）的任何东西 —— 否则回测数字全绿也毫无意义。
本模块的每一条 SQL 都带 `year = ?`，这是有意为之。
"""
import sqlite3

from gaokao_audit import queries
from gaokao_audit.checks import subject_plan
from gaokao_audit.recommend.models import Candidate, Group

BAND = (0.7, 1.3)   # 候选位次带：考生位次的 0.7 ~ 1.3 倍


def candidates(
    conn: sqlite3.Connection,
    cand: Candidate,
    *,
    year: int,
    band: tuple[float, float] = BAND,
) -> list[Group]:
    """筛出候选组。**筛不出就返回空** —— 极端分数段是正常情况，不是错误。"""
    lo, hi = int(cand.rank * band[0]), int(cand.rank * band[1])
    rows = conn.execute(
        "select university_name, major_group, min_score, min_rank "
        "from admission_line "
        "where year = ? and category = ? and min_rank is not null "
        "  and min_rank between ? and ? "
        "order by min_rank, university_name, major_group",
        (int(year), cand.category, lo, hi),
    ).fetchall()

    out: list[Group] = []
    for r in rows:
        g = Group(
            university_name=r[0], major_group=r[1], min_score=r[2], min_rank=r[3],
            subject_req=_requirement(conn, r[0], r[1], year, cand.category),
            category=cand.category,
        )
        if group_is_eligible(conn, g, cand.subjects, year):
            out.append(g)
    return out


def group_is_eligible(
    conn: sqlite3.Connection, group: Group, subjects: tuple[str, ...], year: int
) -> bool:
    """考生的选科能不能报这个组。

    没登记选科要求 = 不限制（数据如此，不该当成"不可报"）。
    """
    if not subjects:
        return True
    plans = queries.enrollment_plan_of(
        conn, group.university_name, group.major_group, year, group.category
    )
    reqs = {p.subject_req for p in plans if p.subject_req}
    if not reqs:
        return True
    return any(subject_plan.satisfied(r, subjects) for r in reqs)


def _requirement(conn, school: str, group: str, year: int, category: str) -> str | None:
    plans = queries.enrollment_plan_of(conn, school, group, year, category)
    reqs = sorted({p.subject_req for p in plans if p.subject_req})
    return "；".join(reqs) if reqs else None
