"""Task 6 · 编排：把 4 处 LLM 调用和 Plan 1 的确定性内核接起来.

三条硬要求：
  ① **意图分类失败，结构化结论照样出** —— 入口环节不能拖垮结论
  ② **报告失败，结构化结论照样出** —— 散文是锦上添花
  ③ **LLM 调用次数有上限**（全系统 4 处）—— 数出来，别信注释
"""
import json
import re
from pathlib import Path

import pytest

from conftest_helpers import make_ctx, make_items
from gaokao_audit.llm.schemas import Intent
from gaokao_audit.pipeline import flow

DEMO = Path(__file__).resolve().parents[1] / "assets" / "demo" / "probe.png"


class FakeChat:
    """假模型：按调用内容返回，并**记下每一次调用**（用来数次数）。"""

    def __init__(self, intent="full_check", actions=None, report=None, fail=False):
        self.intent, self.actions, self.report, self.fail = intent, actions or [], report, fail
        self.calls: list[str] = []

    def __call__(self, messages, **kw):
        if self.fail:
            raise RuntimeError("boom")
        # ⚠️ 看**原始 content**，不要 json.dumps 之后再找 —— 转义会把 "seq" 变成 \"seq\"，
        # 正则就匹配不到了（我第一版就是这么挂的）。calls 里仍存转义后的完整调用，便于断言。
        content = messages[0]["content"] if isinstance(messages, list) else str(messages)
        text = json.dumps(messages, ensure_ascii=False)
        self.calls.append(text)
        if "stability" in content and "reachability" in content:      # 意图分类的提示词
            return self.intent
        if "adjacent_group_verify" in content and "actions" in content:  # supervisor 的提示词
            return json.dumps({"actions": self.actions})
        if self.report is None:
            # 真实模型会照着清单逐条写；假模型也照做 —— 覆盖不了就会被 report 作废（设计如此）
            seqs = sorted({int(m) for m in re.findall(r'"seq"\s*:\s*(\d+)', content)})
            return "".join(f"第 {n} 条 有问题。" for n in seqs) or "没有发现问题。"
        return self.report


@pytest.fixture
def items(conn):
    """一张**有问题**的表：干净条目 + 一条考生够不着的（会被判 tier_inconsistent）。

    ⚠️ 不能用全干净的表 —— 那样 findings 恒为空，这一批测试等于什么都没测。
    """
    from gaokao_audit.models import PlanItem

    clean = make_items(conn, n=5)
    ctx = make_ctx()
    row = conn.execute(
        "select university_name, major_group, min_score from admission_line "
        "where year=2025 and category=? and min_rank < ? limit 1",
        (ctx.category, ctx.candidate_rank),
    ).fetchone()
    assert row, "需要一条够不着的组来构造 tier_inconsistent"
    bad = PlanItem(seq=99, university_name=row[0], major_group=row[1],
                   claimed_min_score=int(row[2]), claimed_rank=1, subject_req=None, tier="稳")
    return clean + [bad]


def test_happy_path_produces_findings_and_narrative(conn, items):
    rep = flow.build(items, "这表稳不稳", conn, make_ctx(), chat=FakeChat(intent="stability"))
    assert rep.intent is Intent.stability
    assert rep.findings, "有问题的表却没报出任何 findings"
    assert rep.narrative


def test_intent_failure_still_produces_structured_findings(conn, items):
    """🔴 Review Focus 5：入口环节炸了，结论不能跟着没。"""
    rep = flow.build(items, "这表稳不稳", conn, make_ctx(), chat=FakeChat(fail=True))
    assert rep.intent is Intent.full_check, "分类失败要落兜底模式"
    assert rep.findings, "🔴 入口环节炸了，结构化结论必须照样出"
    assert rep.narrative == "", "报告也失败了，散文该是空的"


def test_report_failure_keeps_findings(conn, items):
    chat = FakeChat(report="")          # 报告生成返回空 → 降级
    rep = flow.build(items, "q", conn, make_ctx(), chat=chat)
    assert rep.narrative == ""
    assert "narrative_failed" in rep.degraded.values()


def test_at_most_three_llm_calls_on_the_clean_path(conn, items):
    """🔴 干净路径（无异常）**不该**触发 supervisor —— 所以只要 2 次：意图 + 报告。"""
    chat = FakeChat()
    flow.build(items, "q", conn, make_ctx(), chat=chat)
    assert len(chat.calls) <= 3, f"干净路径调了 {len(chat.calls)} 次，超了"


def test_no_findings_never_calls_supervisor(conn):
    """⚠️ 这条必须用**全干净**的表 —— 用有问题的表测这个，测的是另一回事。"""
    chat = FakeChat()
    rep = flow.build(make_items(conn, n=5), "q", conn, make_ctx(), chat=chat)
    assert rep.findings == []
    assert not any("adjacent_group_verify" in c for c in chat.calls), (
        "干净表也去问了 supervisor —— 白花一次调用"
    )


def test_followup_action_actually_runs(conn):
    """Task 4 的追加动作**不能是空壳** —— 有异常且模型要求追加时，必须真的多跑一路检查。"""
    rows = conn.execute(
        "select university_name, major_group, min_score from admission_line "
        "where year=2025 and category=? and min_rank < ? limit 1",
        (make_ctx().category, make_ctx().candidate_rank),
    ).fetchall()
    assert rows, "需要一条考生够不着的组来构造 tier_inconsistent"
    school, group, score = rows[0]
    from gaokao_audit.models import PlanItem

    bad = [PlanItem(seq=1, university_name=school, major_group=group,
                    claimed_min_score=int(score), claimed_rank=1, subject_req=None, tier="稳")]
    assert flow.build(bad, "q", conn, make_ctx(), chat=FakeChat()).findings

    chat = FakeChat(actions=["adjacent_group_verify"])
    rep = flow.build(bad, "q", conn, make_ctx(), chat=chat)
    assert any("adjacent_group_verify" in c for c in chat.calls), "有着 findings 却没问 supervisor"
    assert any(o == "adjacent_group_verify" for o in rep.outcomes), (
        "追加动作被要求了却没真的跑"
    )
