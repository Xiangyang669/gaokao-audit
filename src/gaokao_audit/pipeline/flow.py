"""编排：把 4 处 LLM 调用和 Plan 1 的确定性内核串成一张 LangGraph。

```
START → ① 意图分类（LLM）→ ② 必需检查（0 LLM，Plan 1 的 audit.run）
                                 │
                                 ├─ 有问题 → ③ supervisor（LLM，可跳过）→ 追加检查（0 LLM）
                                 └─ 没问题 → 直接跳过 ③
                                 ↓
                          ④ 报告生成（LLM）
                                 ↓
                                END
```

**「混合式」体现在这里**：② 是**写死的必修项**（保证覆盖 → 可评测），
③ 是在必修项之外**由模型决定要不要追**（提供自主性 → 真 multi-agent）。
两者缺一不可：只有 ② 就是死板的工作流，只有 ③ 就不可测、烧钱。

⚠️ 三次 LLM 调用都在**出错时降级**，任何一处挂掉都不影响结构化结论。
"""
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from gaokao_audit import audit
from gaokao_audit.checks import adjacent_group
from gaokao_audit.llm import client
from gaokao_audit.llm.schemas import Intent
from gaokao_audit.models import AuditContext, Finding, PlanItem
from gaokao_audit.pipeline import followup, intent, report

ChatFn = Callable[..., str]


class _State(TypedDict, total=False):
    """图的 state。

    ⚠️ 必须是 TypedDict，不能图省事写裸 `dict` —— 裸 dict 下节点的返回值**不会合并**进 state，
    表现是下游节点拿不到上游写的键（我第一版就是这么挂的：report 节点 KeyError: 'findings'）。
    """

    question: str
    intent: Any
    findings: list
    outcomes: list
    degraded: dict
    narrative: str

FOLLOWUP_ACTION = "adjacent_group_verify"


@dataclass(frozen=True)
class AuditReport:
    findings: list[Finding]
    narrative: str
    intent: Intent
    outcomes: list[str]                 # 跑过的检查名（含被追加的那一路）
    degraded: dict[str, str] = field(default_factory=dict)


def build(
    items: list[PlanItem],
    question: str,
    conn: sqlite3.Connection,
    ctx: AuditContext,
    *,
    chat: ChatFn | None = None,
) -> AuditReport:
    chat = chat or client.chat
    state = _make_graph(items, conn, ctx, chat).invoke({"question": question})
    return AuditReport(
        findings=state["findings"],
        narrative=state.get("narrative", ""),
        intent=state.get("intent", Intent.full_check),
        outcomes=state.get("outcomes", []),
        degraded=state.get("degraded", {}),
    )


def _make_graph(items, conn, ctx, chat):
    def classify(state):
        # 意图分类自带兜底（入口级不抛），所以这里不需要 try
        return {"intent": intent.classify(state["question"], chat=chat)}

    def run_required(state):
        result = audit.run(items, conn, ctx)
        out = {
            "findings": list(result.findings),
            "outcomes": [o.name for o in result.outcomes],
            "degraded": dict(result.degraded),
        }
        return out

    def supervise(state):
        actions = followup.decide(state["findings"], chat=chat)
        state.setdefault("degraded", {})
        if FOLLOWUP_ACTION not in actions:
            return {}
        flagged = {f.seq for f in state["findings"] if f.kind == "tier_inconsistent"}
        extra = adjacent_group.check(items, conn, ctx, flagged=flagged)
        return {
            "findings": state["findings"] + list(extra.findings),
            "outcomes": state["outcomes"] + [extra.name],
        }

    def write_report(state):
        text = report.render(state["findings"], state["question"], chat=chat)
        degraded = dict(state.get("degraded", {}))
        if state["findings"] and not text:
            # 有发现、却没写出报告 → 散文这一路失败（结论照留）
            degraded["report"] = "narrative_failed"
        return {"narrative": text, "degraded": degraded}

    g = StateGraph(_State)
    g.add_node("classify", classify)
    g.add_node("check", run_required)
    g.add_node("supervise", supervise)
    g.add_node("report", write_report)
    g.add_edge(START, "classify")
    g.add_edge("classify", "check")
    # 🔴 条件边：**没有问题就不叫 supervisor** —— 少一次 LLM 调用，也少一次不确定性
    g.add_conditional_edges(
        "check",
        lambda s: "supervise" if s["findings"] else "report",
        {"supervise": "supervise", "report": "report"},
    )
    g.add_edge("supervise", "report")
    g.add_edge("report", END)
    return g.compile()
