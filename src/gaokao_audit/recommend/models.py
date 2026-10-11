"""推荐层的数据结构。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    """一位考生。`cities` / `majors` 是**偏好**，用来在候选里做匹配。"""

    score: int
    category: str
    rank: int
    subjects: tuple[str, ...] = ()
    cities: tuple[str, ...] = ()
    majors: tuple[str, ...] = ()


@dataclass(frozen=True)
class Group:
    """一个候选的「院校 + 专业组」。**只来自给定年度的真实数据。**"""

    university_name: str
    major_group: str
    min_score: float | None
    min_rank: int | None
    subject_req: str | None
    category: str


@dataclass(frozen=True)
class Recommendation:
    """一条推荐。

    ⚠️ 字段与 Plan 1 的 `PlanItem` 一一对应（多一个 `reason`），
    所以生成的方案**可以直接喂回审计器** —— 那是 Plan 4 的闭环。
    """

    university_name: str
    major_group: str
    tier: str          # 冲 / 稳 / 保
    reason: str
