"""Task 4 · supervisor 追加决策（4 处 LLM 调用之三）.

这一处的**设计价值全在"能省掉"**：没有问题的时候这一整次模型调用就不该发生。
全系统只有 4 处 LLM 调用，其中一处还能经常跳过 —— 这是"省钱即设计"的落点。

另外，追加动作是**闭集**：模型只能从已知的几个里选。开放式的"让它自己决定查什么"
既不可测、也会烧钱。
"""
import json

import pytest

from gaokao_audit.models import Finding
from gaokao_audit.pipeline import followup


def _finding(seq=1, kind="tier_inconsistent"):
    return Finding(seq=seq, kind=kind, detail="d", claimed="稳", actual=1, evidence="e")


def _chat_returning(text):
    return lambda *a, **k: text


def test_no_findings_skips_the_llm_call_entirely():
    """🔴 本任务的核心测试：没有异常就**一次都不要调**。"""
    calls: list = []

    def chat(*a, **k):
        calls.append(1)
        return "[]"

    assert followup.decide([], chat=chat) == []
    assert calls == [], "无异常时仍然调了模型 —— 白花钱"


def test_with_findings_it_does_call_and_returns_actions():
    raw = json.dumps({"actions": ["adjacent_group_verify"]})
    assert followup.decide([_finding()], chat=_chat_returning(raw)) == ["adjacent_group_verify"]


def test_unknown_action_names_are_filtered_out():
    """模型编了一个不存在的动作名 —— 不能让它真的去跑一个不存在的检查。"""
    raw = json.dumps({"actions": ["adjacent_group_verify", "delete_everything", "rm -rf"]})
    assert followup.decide([_finding()], chat=_chat_returning(raw)) == ["adjacent_group_verify"]


def test_plain_list_output_is_accepted():
    assert followup.decide([_finding()], chat=_chat_returning('["adjacent_group_verify"]')) == [
        "adjacent_group_verify"
    ]


def test_failure_degrades_to_no_followup():
    """追加决策失败 = 不追加。**不能**因此让整条链路失败 ——
    追加本来就是锦上添花，Plan 1 的四个检查已经把该报的都报了。"""
    def boom(*a, **k):
        raise RuntimeError("boom")

    assert followup.decide([_finding()], chat=boom) == []


def test_empty_answer_degrades_to_no_followup():
    assert followup.decide([_finding()], chat=_chat_returning("")) == []


def test_deterministic():
    raw = json.dumps({"actions": ["adjacent_group_verify"]})
    a = followup.decide([_finding()], chat=_chat_returning(raw))
    b = followup.decide([_finding()], chat=_chat_returning(raw))
    assert a == b
