"""编排：把四路检查跑完，汇总成一份结果。

两条设计原则：
  ① **一路崩了不能拖垮其余** —— 单路异常记成 `checker_failed`，其余照跑。
     （校验器的价值就在于"至少能报出点什么"，全程崩掉等于什么都没做。）
  ② **输出确定性** —— findings 按 (seq, kind) 排序，同一输入两次跑逐条一致。
"""
import sqlite3
from dataclasses import dataclass

from gaokao_audit.checks import admission_line, rank_conversion, subject_plan, tier_logic
from gaokao_audit.models import AuditContext, CheckOutcome, Finding, PlanItem

CHECKS = (rank_conversion, admission_line, tier_logic, subject_plan)


@dataclass(frozen=True)
class AuditResult:
    findings: list[Finding]
    outcomes: list[CheckOutcome]
    degraded: dict[str, str]

    @property
    def ok(self) -> bool:
        """是不是一次"干净"的审计（没有任何一路出问题）。"""
        return not self.degraded


def run(items: list[PlanItem], conn: sqlite3.Connection, ctx: AuditContext) -> AuditResult:
    outcomes: list[CheckOutcome] = []
    degraded: dict[str, str] = {}

    for module in CHECKS:
        try:
            outcome = module.check(items, conn, ctx)
        except Exception as exc:  # noqa: BLE001 —— 单路故障不许影响其余路
            # ⚠️ **把异常类型也记进去**。一开始只记 "checker_failed"，
            # 结果一个 SQLite 跨线程的 ProgrammingError 表现成"四路全崩、零发现"，
            # 排查时完全没有线索。降级码留下、原因丢掉，等于半个静默。
            degraded[module.NAME] = f"checker_failed:{type(exc).__name__}"
            continue
        outcomes.append(outcome)
        if outcome.degraded:
            degraded[outcome.name] = outcome.degraded

    findings = sorted(
        (f for o in outcomes for f in o.findings), key=lambda f: (f.seq, f.kind)
    )
    return AuditResult(findings=findings, outcomes=outcomes, degraded=degraded)
