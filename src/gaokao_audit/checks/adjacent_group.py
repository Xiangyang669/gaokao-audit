"""追加检查：`adjacent_group_verify`（由 supervisor 决定要不要跑）.

**为什么需要它**：这条追加检查针对的是一类很具体、很常见的错误 ——
**志愿表上的专业组号被读错了**。

截图 OCR / 手抄都可能把「203」读成「205」。后果很隐蔽：
- 组号错了 → 查到的投档线是**另一个组**的 → 判出"够不着却标稳"
- 而系统报出来的是「你这条够不着」，**真实原因却是"组号抄错了"**

做法：对**被判定"够不着"**的那几条，去看同校的**相邻专业组**。
如果有相邻组是够得着的，那大概率是组号读错，而不是考生填错 ——
于是给出一条不同的发现：**可能是组号读错了**，并列出可选的组号。

⚠️ 它是确定性的（零 LLM），所以跑起来不花钱 —— 这也是它值得被追加的原因。
"""
import sqlite3

from gaokao_audit import queries
from gaokao_audit.models import AuditContext, CheckOutcome, Finding, PlanItem

NAME = "adjacent_group_verify"


def check(
    items: list[PlanItem],
    conn: sqlite3.Connection,
    ctx: AuditContext,
    *,
    flagged: set[int],
) -> CheckOutcome:
    if not flagged or ctx.candidate_rank is None:
        return CheckOutcome(NAME, [], None)

    findings: list[Finding] = []
    for it in items:
        if it.seq not in flagged:
            continue
        candidates = _reachable_siblings(conn, it, ctx)
        if not candidates:
            continue
        findings.append(
            Finding(
                seq=it.seq,
                kind="possibly_misread_group",
                detail=(
                    f"第 {it.seq} 条标着专业组 {it.major_group} 且被判定「够不着」，"
                    f"但同校的 {'、'.join(candidates)} 组是够得着的 —— "
                    f"**很可能这一行是组号读错了**，不是考生真的填错"
                ),
                claimed=it.major_group,
                actual=tuple(candidates),
                evidence=f"{ctx.year} 年 {it.university_name} 的可达专业组",
            )
        )
    return CheckOutcome(NAME, findings, None)


def _reachable_siblings(
    conn: sqlite3.Connection, it: PlanItem, ctx: AuditContext
) -> list[str]:
    """同校、同科类、同年里，考生**够得着**（且不是它自己）的专业组号。"""
    rows = conn.execute(
        "select distinct major_group from admission_line "
        "where year = ? and category = ? and university_name = ? "
        "  and major_group <> ? and min_rank is not null and min_rank >= ? "
        "order by major_group limit 5",
        (int(ctx.year), ctx.category, it.university_name,
         it.major_group, int(ctx.candidate_rank)),
    ).fetchall()
    return [str(r[0]) for r in rows]
