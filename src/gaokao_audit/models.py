"""数据结构。查询侧（本文件上半）与检查侧（Task 4 追加）都在这里。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AdmissionLine:
    """一个院校专业组的投档线（由专业录取分聚合到组粒度）。

    ⚠️ **必须有 `category`** —— 同一所学校、同一个专业组号，物理类与历史类的分数线是
    两回事。实测库里存在 6 组「同校同组同年但两科类分数线不同」的组合，缺这一维会串表。
    """

    university_name: str
    major_group: str
    category: str
    year: int
    min_score: float | None
    min_rank: int | None
    subject_req: str | None


@dataclass(frozen=True)
class EnrollmentPlan:
    """招生计划里的一条专业条目（一个专业组下会有多条）。"""

    university_name: str
    major_group: str | None
    major_code: str | None
    major_name: str | None
    subject_req: str | None
    plan_count: int | None
    year: int


@dataclass(frozen=True)
class Rules:
    province: str
    batch: str
    categories: tuple[str, ...]


# ─────────────── 检查侧（Task 4 起）───────────────


@dataclass(frozen=True)
class PlanItem:
    """志愿表里的一条：某校某专业组。"""

    seq: int
    university_name: str
    major_group: str
    claimed_min_score: int | None
    claimed_rank: int | None
    subject_req: str | None
    tier: str  # "冲" / "稳" / "保"


@dataclass(frozen=True)
class Finding:
    """一条被查出来的问题。`claimed` 与 `actual` 要能对照着看。"""

    seq: int
    kind: str
    detail: str
    claimed: object
    actual: object
    evidence: str


@dataclass(frozen=True)
class AuditContext:
    """审计的"考生侧"上下文 —— 它不属于任何一条志愿，是整份表的属性。

    检查③（分档是否自洽）需要考生位次；检查④（选科能不能报）需要考生选科。
    把这些塞进 PlanItem 是错的：每一条都会重复存同一份，且改一处要改 N 处。
    """

    year: int
    category: str
    candidate_rank: int | None = None
    candidate_subjects: tuple[str, ...] = ()


@dataclass(frozen=True)
class CheckOutcome:
    """一路检查的结果。`degraded` 非空表示这一路没查成，**不是**"查了没问题"。"""

    name: str
    findings: list[Finding]
    degraded: str | None
