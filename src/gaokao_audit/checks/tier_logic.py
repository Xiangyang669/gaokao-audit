"""检查③：分档逻辑 —— 冲/稳/保 是否自洽.

**位次数值越大越靠后。** 所以"稳"意味着考生位次应该**小于等于**该组的最低录取位次
（即排在最低线之前）。反过来就是够不着却标"稳"——实测翻车案例正是这个：
考生 18140 位，该组最低 17506 位，却放进"稳"档。

"冲"本来就允许够不着，所以不报。
"""
import sqlite3

from gaokao_audit import queries
from gaokao_audit.models import AuditContext, CheckOutcome, Finding, PlanItem

NAME = "tier_logic"
SAFE_TIERS = ("稳", "保")


def check(items: list[PlanItem], conn: sqlite3.Connection, ctx: AuditContext) -> CheckOutcome:
    if ctx.candidate_rank is None:
        return CheckOutcome(NAME, [], None)  # 不知道考生位次，判不了档，但也不算查失败

    has = conn.execute(
        "select count(*) from admission_line where year = ?", (int(ctx.year),)
    ).fetchone()[0]
    if not has:
        return CheckOutcome(NAME, [], "insufficient_data")

    findings: list[Finding] = []
    for it in items:
        if it.tier not in SAFE_TIERS:
            continue
        line = queries.admission_line_of(
            conn, it.university_name, it.major_group, ctx.year, ctx.category
        )
        if line is None or line.min_rank is None:
            continue
        if ctx.candidate_rank > line.min_rank:
            findings.append(
                Finding(
                    seq=it.seq,
                    kind="tier_inconsistent",
                    detail=(
                        f"标为「{it.tier}」，但考生位次 {ctx.candidate_rank} 比该组最低位次 "
                        f"{line.min_rank} 更靠后（位次数值越大越靠后）—— 实际够不着"
                    ),
                    claimed=it.tier,
                    actual=line.min_rank,
                    evidence=(
                        f"{ctx.year} 年 {it.university_name} 专业组 {it.major_group} "
                        f"最低位次 {line.min_rank}；考生位次 {ctx.candidate_rank}"
                    ),
                )
            )
    return CheckOutcome(NAME, findings, None)
