"""③ 自审闭环：生成 → **用自己的审计器审一遍**。

## 为什么这一步是这个功能的关键

它把「推荐」和「审计」接成**一条链**，而不是两个各说各话的功能：

> 我生成一份方案，**然后用我自己的审计器审它**。

于是推荐有了**两重保障**：
1. **生成时就按规则来**（筛选 → 位次带内、选科符合）
2. **生成后再验一遍**（审计器的那四个检查）

而且这对面试是个天然的自证：**「我生成的东西，自己的审计器说它没问题。」**

⚠️ 生成时用的 `claimed_min_score` / `claimed_rank` 全部取自**库里的真实值**，
所以理论上应该 0 发现。**一旦审出问题，那多半是生成逻辑有 bug —— 要照实报，不要藏。**
"""
import sqlite3
from dataclasses import dataclass, field

from gaokao_audit import audit
from gaokao_audit.models import AuditContext, PlanItem
from gaokao_audit.recommend import compose, screen
from gaokao_audit.recommend.models import Candidate, Recommendation


@dataclass(frozen=True)
class RecommendReport:
    recommendations: list[Recommendation]
    findings: list                      # 来自复用 Plan 1 的 audit.run
    degraded: str | None = None
    outcomes: list = field(default_factory=list)


def build(
    cand: Candidate,
    conn: sqlite3.Connection,
    *,
    year: int,
    n: int = compose.DEFAULT_N,
    chat=None,
) -> RecommendReport:
    groups = screen.candidates(conn, cand, year=year)
    if not groups:
        return RecommendReport([], [], "no_candidates")

    recs = compose.recommend(cand, groups, n=n, chat=chat)
    if not recs:
        return RecommendReport([], [], "compose_failed")

    items = _to_items(recs, groups)
    ctx = AuditContext(
        year=year, category=cand.category,
        candidate_rank=cand.rank, candidate_subjects=cand.subjects,
    )
    result = audit.run(items, conn, ctx)
    return RecommendReport(
        recommendations=recs,
        findings=list(result.findings),
        degraded=None,
        outcomes=[o.name for o in result.outcomes],
    )


def _to_items(recs: list[Recommendation], groups) -> list[PlanItem]:
    """把推荐转成审计器的输入。

    ⚠️ `claimed_min_score` / `claimed_rank` 取自**库里的真实值**（不是模型给的）——
    否则就是在拿模型编的数字去审模型编的方案。这正是"生成时按规则来"的意思。
    """
    by_key = {(g.university_name, g.major_group): g for g in groups}
    items: list[PlanItem] = []
    for i, r in enumerate(recs, start=1):
        g = by_key[(r.university_name, r.major_group)]
        items.append(
            PlanItem(
                seq=i,
                university_name=g.university_name,
                major_group=g.major_group,
                claimed_min_score=int(g.min_score) if g.min_score is not None else None,
                claimed_rank=g.min_rank,
                subject_req=g.subject_req,
                tier=r.tier,
            )
        )
    return items
