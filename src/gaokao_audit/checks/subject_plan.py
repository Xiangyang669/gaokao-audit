"""检查④：选科能不能报.

⚠️ **真实数据里 `subject_req` 有两种格式**（按年份不同，见 docs/data-schema.md）：
  - 2022 / 2024：`首选物理，再选化学` / `首选物理，再选不限`
  - 2025：       `不限` / `化学` / `地理` / `化学和生物`   ← **丢了"首选X"前缀**

只认第一种的解析器碰上第二种会**一律判为"满足"** —— 检查静默失效、永远报不出问题。
所以这里两种都解析，并且把 `化学/生物(2选1)` 当成**或**（不是同时要）。

一个专业组下可能有多个专业、要求不同：**只要有一条专业的选科要求能被满足**，这个组就能报。
"""
import re
import sqlite3

from gaokao_audit import queries
from gaokao_audit.models import AuditContext, CheckOutcome, Finding, PlanItem

NAME = "subject_plan"
_SPLIT = re.compile(r"[，,、;；]")
_ORDINAL = re.compile(r"\((\d+)\s*选\s*(\d+)\)")


def check(items: list[PlanItem], conn: sqlite3.Connection, ctx: AuditContext) -> CheckOutcome:
    if not ctx.candidate_subjects:
        return CheckOutcome(NAME, [], None)  # 不知道考生选科，判不了

    findings: list[Finding] = []
    for it in items:
        plans = queries.enrollment_plan_of(
            conn, it.university_name, it.major_group, ctx.year, ctx.category
        )
        reqs = {p.subject_req for p in plans if p.subject_req}
        if not reqs:
            continue  # 该组没登记选科要求（或该年没计划）—— 正常，跳过
        if any(satisfied(r, ctx.candidate_subjects) for r in reqs):
            continue
        findings.append(
            Finding(
                seq=it.seq,
                kind="subject_not_allowed",
                detail=(
                    f"考生选科 {'/'.join(ctx.candidate_subjects)} 不满足该组任何专业的选科要求"
                    f"（{'；'.join(sorted(reqs))}）"
                ),
                claimed=tuple(ctx.candidate_subjects),
                actual=tuple(sorted(reqs)),
                evidence="；".join(sorted(reqs)),
            )
        )
    return CheckOutcome(NAME, findings, None)


def satisfied(requirement: str, subjects: tuple[str, ...]) -> bool:
    """判断考生的选科能不能满足某条要求。两种格式都能解析。"""
    text = (requirement or "").strip()
    if not text or text == "不限":
        return True

    groups: list[tuple[str, list[str]]] = []
    for token in (t.strip() for t in _SPLIT.split(text)):
        if not token:
            continue
        if token.startswith("首选"):
            value = token[2:].strip()
            if value and value != "不限":
                groups.append(("all", [value]))
        elif token.startswith("再选"):
            value = token[2:].strip()
            if value and value != "不限":
                groups.append(_parse_group(value))
        else:
            # 2025 的格式：整段就是再选科目（比如 `化学` / `化学和生物`）
            groups.append(_parse_group(token))

    if not groups:
        return True
    for mode, values in groups:
        if not values:
            continue
        hit = [v for v in values if v in subjects]
        if mode == "all" and len(hit) != len(values):
            return False
        if mode == "any" and not hit:
            return False
    return True


def _parse_group(text: str) -> tuple[str, list[str]]:
    """`化学/生物(2选1)` → ('any', ['化学','生物'])；`化学和生物` → ('all', [...])。"""
    cleaned = _ORDINAL.sub("", text).strip()
    if "和" in cleaned:
        return "all", [x.strip() for x in cleaned.split("和") if x.strip()]
    for sep in ("/", "或"):
        if sep in cleaned:
            return "any", [x.strip() for x in cleaned.split(sep) if x.strip()]
    return "all", [cleaned] if cleaned else []
