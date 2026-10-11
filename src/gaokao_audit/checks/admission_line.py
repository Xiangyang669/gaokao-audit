"""检查②：投档线核对 —— 表里声称的最低分跟真实值对不上.

注意一个容易搞错的边界：**某个组在某年不招生是正常的**（专业调整、停招），
那种情况要**跳过**，不能报成"抄错了"。只有"库里明明有这个组、数字却对不上"才是问题。
"""
import sqlite3

from gaokao_audit import config, queries
from gaokao_audit.models import AuditContext, CheckOutcome, Finding, PlanItem

NAME = "admission_line"


def check(items: list[PlanItem], conn: sqlite3.Connection, ctx: AuditContext) -> CheckOutcome:
    has = conn.execute(
        "select count(*) from admission_line where year = ?", (int(ctx.year),)
    ).fetchone()[0]
    if not has:
        return CheckOutcome(NAME, [], "insufficient_data")

    findings: list[Finding] = []
    for it in items:
        if it.claimed_min_score is None:
            continue
        line = queries.admission_line_of(
            conn, it.university_name, it.major_group, ctx.year, ctx.category
        )
        if line is None or line.min_score is None:
            continue  # 该组该年不在库里 —— 正常，不是问题
        if abs(line.min_score - it.claimed_min_score) <= config.LINE_TOLERANCE:
            continue
        findings.append(
            Finding(
                seq=it.seq,
                kind="line_mismatch",
                detail=(
                    f"声称最低分 {it.claimed_min_score}，{ctx.year} 年库里是 {line.min_score}"
                    f"（差 {abs(line.min_score - it.claimed_min_score):.0f} 分）"
                ),
                claimed=it.claimed_min_score,
                actual=line.min_score,
                evidence=f"{ctx.year} 年投档线：{it.university_name} 专业组 {it.major_group}",
            )
        )
    return CheckOutcome(NAME, findings, None)
