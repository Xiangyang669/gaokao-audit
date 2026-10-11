"""错误注入：往一张**干净**的志愿表里塞进**已知**的错误。

为什么要这么做：校验器没法用"人工标注的正确答案"来衡量 ——
但可以说「我往表里塞了 N 个我知道的错误，它抓到了几个」。这就是 recall 的来源。

四类注入（每一类都对应一个真实产品犯过的错）：
  year    —— 把位次换成用**另一年**的表算出来的   → 期望 rank_year_mismatch
  number  —— 把声称的最低分改动几十份             → 期望 line_mismatch
  tier    —— 把"冲"标成"稳"（而考生够不着）       → 期望 tier_inconsistent
  subject —— 把考生的选科换成一个不满足的组合     → 期望 subject_not_allowed

⚠️ `subject` 动的是 **ctx**（考生选科），不是某一条志愿 —— 考生侧信息本来就不属于单条。
   所以注入作用在 `Case(items, ctx)` 上，返回值也是 Case。
"""
import random
import sqlite3
from dataclasses import dataclass, replace

from gaokao_audit import config, queries
from gaokao_audit.models import AuditContext, PlanItem

EXPECTED = {
    "year": "rank_year_mismatch",
    "number": "line_mismatch",
    "tier": "tier_inconsistent",
    "subject": "subject_not_allowed",
}

_SCORE_SHIFT = 30  # "number" 类改动的分数幅度（远大于 LINE_TOLERANCE）


@dataclass(frozen=True)
class Case:
    items: list[PlanItem]
    ctx: AuditContext


@dataclass(frozen=True)
class Injected:
    seq: int
    kind: str
    expected_finding_kind: str


def inject(
    case: Case, conn: sqlite3.Connection, kind: str, rng: random.Random, n: int | None = None
) -> tuple[Case, list[Injected]]:
    """返回 (注入后的 Case, 注入记录)。**可复现**：同一个 rng 种子给同样的结果。"""
    if kind not in EXPECTED:
        raise ValueError(f"未知的注入类型：{kind}")

    items = list(case.items)
    ctx = case.ctx
    if kind == "subject":
        ctx = replace(ctx, candidate_subjects=_bad_subjects(ctx, conn, items))
        picked = items if n is None else items[:n]
        return Case(items, ctx), [Injected(i.seq, kind, EXPECTED[kind]) for i in picked]

    idx = list(range(len(items)))
    rng.shuffle(idx)
    pick = idx if n is None else idx[:n]

    injected: list[Injected] = []
    for i in pick:
        it = items[i]
        changed = _mutate(it, kind, conn, ctx, rng)
        if changed is None:
            continue
        items[i] = changed
        injected.append(Injected(it.seq, kind, EXPECTED[kind]))
    return Case(items, ctx), sorted(injected, key=lambda x: x.seq)


def _mutate(it: PlanItem, kind: str, conn, ctx: AuditContext, rng: random.Random):
    if kind == "number":
        if it.claimed_min_score is None:
            return None
        shift = _SCORE_SHIFT * (1 if rng.random() < 0.5 else -1)
        return replace(it, claimed_min_score=it.claimed_min_score + shift)

    if kind == "year":
        if it.claimed_min_score is None:
            return None
        others = [y for y in config.SCORE_YEARS if y != ctx.year]
        rng.shuffle(others)
        for y in others:
            rank = queries.rank_of(conn, it.claimed_min_score, ctx.category, y)
            if rank is not None:
                return replace(it, claimed_rank=rank)
        return None

    if kind == "tier":
        # ⚠️ tier_logic 看的是**考生位次** vs 该组最低位次，**不看这条志愿自己的字段**。
        # 所以"把档位改坏"不能靠改 claimed_rank —— 得把这条换成**一个考生够不着的组**的真实数据，
        # 再把它标成「稳」。换过去的其余字段都用真实值，保证只有档位这一处是坏的。
        if ctx.candidate_rank is None:
            return None
        row = conn.execute(
            "select university_name, major_group, min_score from admission_line "
            "where year = ? and category = ? and min_rank is not null and min_rank < ? "
            "order by min_rank desc limit 1",
            (int(ctx.year), ctx.category, int(ctx.candidate_rank)),
        ).fetchone()
        if row is None:
            return None
        school, group, score = row
        return replace(
            it,
            university_name=school,
            major_group=group,
            claimed_min_score=int(score),
            claimed_rank=queries.rank_of(conn, int(score), ctx.category, ctx.year),
            tier="稳",
        )

    return None


def _bad_subjects(ctx: AuditContext, conn, items: list[PlanItem]) -> tuple[str, ...]:
    """挑一组"肯定不满足表里所有要求"的选科 —— 故意跟要求完全不重叠。"""
    mentioned: set[str] = set()
    for it in items:
        for p in queries.enrollment_plan_of(
                conn, it.university_name, it.major_group, ctx.year, ctx.category
            ):
            if p.subject_req:
                mentioned.update(_subjects_in(p.subject_req))
    pool = [s for s in ("物理", "化学", "生物", "政治", "地理", "历史") if s not in mentioned]
    return tuple(pool[:3]) or ("历史", "政治", "地理")


def _subjects_in(requirement: str) -> set[str]:
    return {s for s in ("物理", "化学", "生物", "政治", "地理", "历史") if s in requirement}
