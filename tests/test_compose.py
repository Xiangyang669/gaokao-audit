"""Task 2 · LLM 排序组合 + 理由（第 5 处 LLM 调用）.

**模型只在已筛出的候选里挑与排** —— 它做的是规则做不到的事（偏好匹配 + 说理由），
不做算术。所以这里最要紧的两条护栏是：
  · 它不能"发明"候选之外的院校（Review Focus 4）
  · 它挑的每一条都要说得出为什么
"""
import json

import pytest

from gaokao_audit.recommend import compose
from gaokao_audit.recommend.models import Candidate, Group

GROUPS = [
    Group("暨南大学", "201", 612, 18043, "首选物理，再选化学", "物理类"),
    Group("华南师范大学", "203", 598, 27615, "首选物理，再选不限", "物理类"),
    Group("广东工业大学", "202", 570, 51302, "首选物理，再选不限", "物理类"),
]
CAND = Candidate(score=600, category="物理类", rank=20000,
                 subjects=("物理", "化学", "生物"), cities=("广州",), majors=("计算机",))


def _chat(payload):
    return lambda *a, **k: json.dumps(payload, ensure_ascii=False)


def _rec(school, group, tier="稳", reason="位次匹配"):
    return {"university_name": school, "major_group": group, "tier": tier, "reason": reason}


def test_invented_schools_are_filtered_out():
    """🔴 Review Focus 4：候选之外的名字一律丢掉 —— 否则等于它在编。"""
    raw = {"recommendations": [
        _rec("暨南大学", "201"),
        _rec("清华大学", "999"),          # 候选里没有，是模型编的
    ]}
    out = compose.recommend(CAND, GROUPS, chat=_chat(raw))
    assert [r.university_name for r in out] == ["暨南大学"], f"编造的院校没被过滤：{out}"


def test_group_must_be_in_the_candidates_too():
    """光校名对上不够 —— (校名, 专业组) 这一对必须真在候选里。"""
    out = compose.recommend(CAND, GROUPS, chat=_chat({"recommendations": [_rec("暨南大学", "777")]}))
    assert out == []


def test_every_recommendation_carries_a_reason():
    """「为什么推荐它」是这个功能的价值所在 —— 空理由不算数。"""
    raw = {"recommendations": [_rec("暨南大学", "201", reason=""), _rec("广东工业大学", "202")]}
    out = compose.recommend(CAND, GROUPS, chat=_chat(raw))
    assert out and all(r.reason.strip() for r in out)


def test_output_is_capped_at_n():
    """⚠️ 要用**不同**的候选来测上限 —— 重复项会先被去重（去重在前、截断在后）。"""
    three = {"recommendations": [_rec("暨南大学", "201"), _rec("华南师范大学", "203"),
                                _rec("广东工业大学", "202")]}
    assert len(compose.recommend(CAND, GROUPS, n=2, chat=_chat(three))) == 2
    assert len(compose.recommend(CAND, GROUPS, n=99, chat=_chat(three))) == 3


def test_empty_candidates_skips_the_call_entirely():
    """没候选就别调模型 —— 白花钱，而且它只能编。"""
    calls = []

    def chat(*a, **k):
        calls.append(1)
        return "{}"

    assert compose.recommend(CAND, [], chat=chat) == []
    assert calls == []


def test_call_failure_degrades_to_empty():
    def boom(*a, **k):
        raise RuntimeError("boom")

    assert compose.recommend(CAND, GROUPS, chat=boom) == []


def test_bad_json_degrades_to_empty():
    assert compose.recommend(CAND, GROUPS, chat=lambda *a, **k: "这不是 JSON") == []


def test_duplicates_are_deduplicated():
    raw = {"recommendations": [_rec("暨南大学", "201"), _rec("暨南大学", "201")]}
    assert len(compose.recommend(CAND, GROUPS, chat=_chat(raw))) == 1
