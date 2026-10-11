"""Task 1 · A2A 适配库可用性（spec §13 未验证前提②）.

只断言最低限度的两件事：**能建出 card**、**card 里声明了 skills**。
协议细节交给库；我们自己要保证的是"外部 agent 照着 card 调用，拿到的是我们真有的能力"。
"""
import pytest

from gaokao_audit.api import a2a


def test_agent_card_is_served():
    card = a2a.agent_card(base_url="http://127.0.0.1:8000")
    assert card["name"]
    assert card["skills"], "card 必须声明 skills —— 否则外部 agent 不知道它能干什么"


def test_card_declares_the_skill_we_actually_have():
    card = a2a.agent_card(base_url="http://127.0.0.1:8000")
    ids = {s["id"] for s in card["skills"]}
    assert "check_volunteer_plan" in ids


def test_card_says_it_does_not_recommend():
    """🔴 边界必须写进 card：这个 agent **只审计、不推荐**。
    外部 agent 照着 card 调用，不能以为它能出志愿方案。"""
    card = a2a.agent_card(base_url="http://127.0.0.1:8000")
    text = (card["description"] + " " + " ".join(s["description"] for s in card["skills"]))
    assert "审计" in text and "不" in text
