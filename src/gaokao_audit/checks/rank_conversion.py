"""检查①：位次换算.

要抓的失败模式（大厂实测翻过车）：
  用**别的年份**的一分一段表算位次 —— 分数看起来对，位次却前拉/后拉了上千名，
  据此判"稳/冲"必然错。

做法：拿条目里声称的 (分数, 位次)，用**基准年**的表重算一遍。
  对不上 → 再去别的年份的表里找 —— 如果跟某一年对得上，就**指名道姓**说是那一年的表。
"""
import sqlite3

from gaokao_audit import config, queries
from gaokao_audit.models import AuditContext, CheckOutcome, Finding, PlanItem

NAME = "rank_conversion"


def check(items: list[PlanItem], conn: sqlite3.Connection, ctx: AuditContext) -> CheckOutcome:
    # 基准年的表在不在？不在就整路降级，不逐条瞎报。
    if queries.rank_of(conn, 600, ctx.category, ctx.year) is None:
        return CheckOutcome(NAME, [], "insufficient_data")

    findings: list[Finding] = []
    for it in items:
        if it.claimed_min_score is None or it.claimed_rank is None:
            continue
        actual = queries.rank_of(conn, it.claimed_min_score, ctx.category, ctx.year)
        if actual is None:
            # ⚠️ 这里必须 `continue` 而不是整路 `return`：
            # 一个分数越出当年一分一段表的范围（该科类没有这一档），只是**这一条**查不了，
            # 不该把整路标成"数据不足"、更不该把已经收集到的其它 finding 一起丢掉。
            # （另外三个检查对缺数据条目也是逐条跳过，保持一致。）
            continue
        if abs(actual - it.claimed_rank) <= _tolerance(conn, it, ctx):
            continue

        other = _year_it_matches(conn, it, ctx)
        if other is not None:
            findings.append(
                Finding(
                    seq=it.seq,
                    kind="rank_year_mismatch",
                    detail=(
                        f"位次 {it.claimed_rank} 与 {ctx.year} 年的表不符（该分数应为 {actual}），"
                        f"但与该分数在 {other} 年的位次一致 —— 看起来用的是 {other} 年的表"
                    ),
                    claimed=it.claimed_rank,
                    actual=actual,
                    evidence=f"{ctx.year} 年{ctx.category}一分一段表",
                )
            )
        else:
            findings.append(
                Finding(
                    seq=it.seq,
                    kind="rank_mismatch",
                    detail=(
                        f"位次 {it.claimed_rank} 与 {ctx.year} 年{ctx.category}的表不符"
                        f"（应为 {actual}）"
                    ),
                    claimed=it.claimed_rank,
                    actual=actual,
                    evidence=f"{ctx.year} 年{ctx.category}一分一段表",
                )
            )
    return CheckOutcome(NAME, findings, None)


def _tolerance(conn, it: PlanItem, ctx: AuditContext) -> int:
    """容差 = max(固定下限, 该分数段的段内人数)。

    ⚠️ **不能写死成一个小常数。** 这是脚本 make_demo 真跑时踩出来的：
    投档表里的位次是「**投档最低排位**」（最后一个被录取者的名次），
    而这里算的是「**该分数的段末位**」—— 同一个分数有几百上千人，
    两者合法地差出几百名，写死容差 5 会报一堆假阳性。

    段内人数就是"同分最多能差多少"的物理上界，用它当容差是**有依据的**，
    而不是"把阈值调大让它别报"。
    """
    seg = queries.segment_size(conn, it.claimed_min_score, ctx.category, ctx.year)
    return max(config.RANK_TOLERANCE, seg or 0)


def _year_it_matches(conn, it: PlanItem, ctx: AuditContext) -> int | None:
    """声称的位次像哪一年的表算出来的。都没有 → None。"""
    for y in config.SCORE_YEARS:
        if y == ctx.year:
            continue
        r = queries.rank_of(conn, it.claimed_min_score, ctx.category, y)
        if r is not None and abs(r - it.claimed_rank) <= config.RANK_TOLERANCE:
            return y
    return None
