"""Task 5 · 报告生成（4 处 LLM 调用之四）.

测试策略（这个项目的一贯立场）：**断言结构，不断言措辞**。
模型每次说话都不一样，断言具体句子＝测试随机红绿。
能断言的是：**它不许漏掉任何一条发现**、**失败时不许假装成功**。
"""
import pytest

from gaokao_audit.models import Finding
from gaokao_audit.pipeline import report


def _f(seq, kind="tier_inconsistent"):
    return Finding(seq=seq, kind=kind, detail=f"第{seq}条的问题",
                   claimed="稳", actual=100, evidence="2025 年投档线")


def _chat_returning(text):
    return lambda *a, **k: text


def test_report_covers_every_finding():
    """🔴 核心断言：报告可以说得不一样，但**不许漏**。"""
    findings = [_f(1), _f(2), _f(3)]
    good = "第 1 条 有问题。第 2 条 有问题。第 3 条 有问题。"
    text = report.render(findings, "这表稳不稳", chat=_chat_returning(good))
    for f in findings:
        assert f"第 {f.seq} 条" in text, f"报告漏掉了第 {f.seq} 条"


def test_incomplete_report_is_rejected_not_silently_accepted():
    """模型只写了第 1 条 —— 这份报告**不能**就这么交出去。

    漏报比措辞难看严重得多：用户会以为"只有一处问题"。
    宁可退回结构化结果，也不要一份看起来完整、其实漏了的散文。
    """
    findings = [_f(1), _f(2), _f(3)]
    partial = "第 1 条 有问题。"
    text = report.render(findings, "这表稳不稳", chat=_chat_returning(partial))
    assert text == "", "漏条的报告被当成有效输出返回了"


def test_no_findings_still_produces_a_sentence():
    text = report.render([], "这表稳不稳", chat=_chat_returning("没有发现问题。"))
    assert text


def test_call_failure_returns_empty_string():
    """Review Focus 5：报告失败要降级成空串，由上层标 narrative_failed。
    **结论（结构化 findings）不能因为散文没了就丢。**"""
    def boom(*a, **k):
        raise RuntimeError("DeepSeek 请求失败（URLError）")

    assert report.render([_f(1)], "这表稳不稳", chat=boom) == ""


def test_empty_answer_returns_empty_string():
    assert report.render([_f(1)], "这表稳不稳", chat=_chat_returning("")) == ""


def test_deterministic():
    good = "第 1 条 有问题。"
    a = report.render([_f(1)], "q", chat=_chat_returning(good))
    b = report.render([_f(1)], "q", chat=_chat_returning(good))
    assert a == b
