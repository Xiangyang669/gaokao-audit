"""Task 3 · 自审闭环：**生成的方案，立刻用自己的审计器审一遍**.

这是把「推荐」和「审计」接成**一条链**的地方 —— 而不是两个各说各话的功能。
面试时能说：「我生成了一份方案，然后用我自己的审计器审它。」
"""
import json

import pytest

from gaokao_audit.recommend import flow as rec_flow
from gaokao_audit.recommend.models import Candidate

CAND = Candidate(score=600, category="物理类", rank=20000,
                 subjects=("物理", "化学", "生物"), cities=("广州",), majors=("计算机",))
Y = 2025


class FakeChat:
    """假模型：从**实际给出的候选**里挑前几条，按位次关系给档位 —— 模拟一个守规矩的模型。"""

    def __init__(self, force_tier=None):
        self.force_tier = force_tier
        self.calls = 0

    def __call__(self, messages, **kw):
        self.calls += 1
        content = messages[0]["content"] if isinstance(messages, list) else str(messages)
        m = content.split("候选（只能从这里选")[-1]
        # ⚠️ 必须取**第一个 [ 之后的第一个 ]**：提示词末尾还有个输出示例，
        # 里面也有 ]，用 rfind 会把示例一起吃进来（Extra data）。
        start = m.find("[")
        end = m.find("]", start)
        groups = json.loads(m[start:end + 1])
        cand_rank = int(content.split("全省位次 **")[1].split("**")[0])
        recs = []
        for g in groups[:5]:
            if self.force_tier == "bad":
                tier = "稳"           # 故意把够不着的也标"稳" → 自审应该报出来
            else:
                tier = "冲" if (g["min_rank"] or 0) < cand_rank else "保"
            recs.append({"university_name": g["university_name"], "major_group": g["major_group"],
                         "tier": tier, "reason": f"位次 {g['min_rank']} 与考生相近"})
        return json.dumps({"recommendations": recs}, ensure_ascii=False)


def test_flow_returns_both_recommendations_and_audit_findings(conn):
    rep = rec_flow.build(CAND, conn, year=Y, chat=FakeChat())
    assert rep.recommendations, "没生成任何推荐"
    assert isinstance(rep.findings, list), "闭环断了：生成的方案没有被审计"


def test_a_clean_generation_produces_zero_findings(conn):
    """🔴 Review Focus 3：生成时是按规则来的，理论上应该 **0 发现**。"""
    rep = rec_flow.build(CAND, conn, year=Y, chat=FakeChat())
    assert rep.findings == [], (
        "生成器按规则走却审出了问题 —— 要么生成逻辑错了，要么审计器误报：" 
        + "; ".join(f"{f.seq}:{f.kind}" for f in rep.findings)
    )


def test_a_wrong_tier_is_caught_by_our_own_auditor(conn):
    """反向证明这条闭环**真的在审**，不是摆设 —— 故意标错档位必须被抓。"""
    rep = rec_flow.build(CAND, conn, year=Y, chat=FakeChat(force_tier="bad"))
    assert any(f.kind == "tier_inconsistent" for f in rep.findings), (
        "故意标错的档位没被自己的审计器抓到 —— 闭环是假的"
    )


def test_empty_candidates_degrades_cleanly(conn):
    far = Candidate(score=750, category="物理类", rank=1, subjects=("物理",))
    rep = rec_flow.build(far, conn, year=Y, chat=FakeChat())
    assert rep.recommendations == [] and rep.degraded == "no_candidates"
