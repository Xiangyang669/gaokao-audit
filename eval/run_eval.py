"""评测 harness：注入已知错误 → 跑审计 → 量检出率 / 误报率。

跑法： py eval/run_eval.py [--n 50]
"""
import argparse
import json
import random
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))   # gaokao_audit
sys.path.insert(0, str(_ROOT))           # 让 `eval` 这个包能被 import（直接跑脚本时 sys.path[0] 是 eval/）

from gaokao_audit import audit, config, db  # noqa: E402
from eval import inject  # noqa: E402

# 🔴 spec §10.5 纪律①：样本量门槛。项目① 栽在"18 道题撑不起结论"，这里不重蹈。
SAMPLE_FLOOR = 50
_CHECKABLE_KINDS = set(inject.EXPECTED.values())


@dataclass
class EvalReport:
    recall: float
    precision: float
    per_kind: dict[str, float]
    missed_kinds: list[str]
    baseline_findings: int | None = None
    warnings: list[str] = field(default_factory=list)


def run(case: inject.Case, conn: sqlite3.Connection, n_per_kind: int = SAMPLE_FLOOR) -> EvalReport:
    warnings: list[str] = []
    if n_per_kind < SAMPLE_FLOOR:
        warnings.append(
            f"每类只注入 {n_per_kind} 条，低于门槛 {SAMPLE_FLOOR} —— 结论会落在噪声里，别写进报告"
        )

    baseline = audit.run(case.items, conn, case.ctx)
    baseline_findings = len(baseline.findings)

    total_inj = 0
    detected = 0
    reported = 0
    true_pos = 0
    per_kind: dict[str, float] = {}

    for kind in inject.EXPECTED:
        bad_case, injected = inject.inject(case, conn, kind, random.Random(20261011), n=n_per_kind)
        result = audit.run(bad_case.items, conn, bad_case.ctx)
        # ⚠️ 只统计「可注入的那四类」finding。像 number 注入（改了分数没改位次）
        # 会**连带**产生一条真实的 rank_mismatch —— 那是真问题、不是误报，
        # 把它算进 precision 的分母会系统性压低精确率。
        found = {(f.seq, f.kind) for f in result.findings if f.kind in _CHECKABLE_KINDS}
        want = {(i.seq, i.expected_finding_kind) for i in injected}

        hit = len(found & want)
        per_kind[kind] = (hit / len(injected)) if injected else 0.0
        total_inj += len(injected)
        detected += hit
        reported += sum(1 for f in result.findings if f.kind in _CHECKABLE_KINDS)
        true_pos += len(found & want)

    recall = (detected / total_inj) if total_inj else 0.0
    precision = (true_pos / reported) if reported else 1.0
    missed = [k for k, v in per_kind.items() if v == 0.0]

    return EvalReport(
        recall=recall, precision=precision, per_kind=per_kind, missed_kinds=missed,
        baseline_findings=baseline_findings, warnings=warnings,
    )


BAD_CASES = Path(__file__).resolve().parent / "badcases.json"


@dataclass
class BadcaseReport:
    """回答一个具体问题：真实世界里已发生过的每一类错，本系统抓得到吗？"""

    recall: float
    caught_kinds: set[str]
    blind_spots: list[dict]
    per_kind: dict[str, float]


def run_badcases(
    conn: sqlite3.Connection, case: inject.Case, n_per_kind: int = SAMPLE_FLOOR
) -> BadcaseReport:
    """用真实 badcase 集给系统打分.

    ⚠️ 这里**不是逐条重放**那些真实错误（原始的表和考生数据拿不到），
       而是验证「**那一类**错误，对应的检查抓不抓得到」——
       靠的仍然是错误注入，但目标由真实事件来定义。
    """
    cases = json.loads(BAD_CASES.read_text(encoding="utf-8"))
    rep = run(case, conn, n_per_kind=n_per_kind)
    # ⚠️ 注意换算：per_kind 的键是**注入类别**（year/number/tier/subject），
    # 而 badcase 映射的是**finding 类别**（rank_year_mismatch/...）。两者别混。
    caught = {inject.EXPECTED[k] for k, v in rep.per_kind.items() if v > 0}

    needed = {c["expected_finding_kind"] for c in cases if c.get("expected_finding_kind")}
    blind = [c for c in cases if not c.get("expected_finding_kind")]
    recall = (len(needed & caught) / len(needed)) if needed else 0.0

    return BadcaseReport(
        recall=recall, caught_kinds=caught, blind_spots=blind, per_kind=rep.per_kind
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=SAMPLE_FLOOR, help="每类注入多少条")
    ap.add_argument("--db", default=str(config.DB_PATH))
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from conftest_helpers import make_ctx, make_items  # noqa: PLC0415

    conn = db.connect(Path(args.db))
    case = inject.Case(items=make_items(conn, n=max(args.n, SAMPLE_FLOOR) + 10), ctx=make_ctx())
    rep = run(case, conn, n_per_kind=args.n)

    print("=" * 66)
    print(f"样本：{len(case.items)} 条志愿 · 每类注入 {args.n} 条")
    print("-" * 66)
    print(f"干净表基线误报         : {rep.baseline_findings}")
    print(f"检出率 recall          : {rep.recall:.3f}")
    print(f"精确率 precision       : {rep.precision:.3f}")
    for k, v in sorted(rep.per_kind.items()):
        print(f"    {k:<8} recall = {v:.3f}")
    print(f"抓不到的类别            : {rep.missed_kinds or '（无）'}")
    for w in rep.warnings:
        print(f"⚠️  {w}")
    print("=" * 66)


if __name__ == "__main__":
    main()
