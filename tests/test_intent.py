"""Task 3 · 意图分类（4 处 LLM 调用之二）.

Review Focus 5：分类失败要**落兜底模式**，不能整条链路 500。
分类错了不可怕（顶多审得宽一点），链路断了才可怕。
"""
import json

import pytest

from gaokao_audit.llm.schemas import Intent
from gaokao_audit.pipeline import intent


def _chat_returning(text):
    return lambda *a, **k: text


def test_valid_label_is_parsed_offline():
    """走真 client（命中缓存）。"""
    got = intent.classify("我这表稳不稳，会不会滑档")
    assert got is Intent.stability


@pytest.mark.parametrize("raw,expected", [
    ("stability", Intent.stability),
    ('{"intent": "reachability"}', Intent.reachability),
    ("  full_check\n", Intent.full_check),
    ("答案：stability", Intent.stability),
])
def test_various_output_shapes_are_accepted(raw, expected):
    """模型可能只回标签、回 JSON、回带前缀的话 —— 都要认。"""
    assert intent.classify("随便问", chat=_chat_returning(raw)) is expected


def test_unknown_answer_falls_back_to_full_check():
    assert intent.classify("随便问", chat=_chat_returning("???")) is Intent.full_check


def test_empty_answer_falls_back_to_full_check():
    assert intent.classify("随便问", chat=_chat_returning("")) is Intent.full_check


def test_call_failure_falls_back_to_full_check():
    """🔴 Review Focus 5：调用失败**不能**让链路断掉。"""
    def boom(*a, **k):
        raise RuntimeError("DeepSeek 请求失败（URLError）")

    assert intent.classify("随便问", chat=boom) is Intent.full_check


def test_never_raises_for_any_input():
    """任何输入都不许抛 —— 这一处是"入口级"的，它炸了整条链路就炸了。"""
    for q in ("", "   ", "🙂", "x" * 5000):
        assert intent.classify(q, chat=_chat_returning("stability")) in set(Intent)
