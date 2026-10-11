"""Task 4 · 回测：用 2022 的参照给"考生"生成方案，用 2025 的真实结果检验.

🔴 **本计划最重要的一条测试在这里**：回测绝不许偷看未来。
   给 2022 生成方案时若读了 2025 的数据，数字全绿也毫无意义 —— 那是作弊，不是回测。
"""
import json

import pytest

from gaokao_audit.recommend import screen
from eval import backtest

FIT, TEST = 2022, 2025


class RecordingConn:
    """把每次查询记下来 —— 用来证明"生成阶段没碰检验年"。"""

    def __init__(self, conn):
        self._c = conn
        self.calls: list[tuple] = []

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        return self._c.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._c, name)


@pytest.fixture
def fake_chat():
    """守规矩的假模型：只从候选里挑，按位次关系给档。"""
    def _chat(messages, **kw):
        content = messages[0]["content"] if isinstance(messages, list) else str(messages)
        m = content.split("候选（只能从这里选")[-1]
        s = m.find("[")
        groups = json.loads(m[s:m.find("]", s) + 1])
        return json.dumps({"recommendations": [
            {"university_name": g["university_name"], "major_group": g["major_group"],
             "tier": "稳", "reason": f"位次 {g['min_rank']} 与他相近"}
            for g in groups[:5]
        ]}, ensure_ascii=False)
    return _chat


def test_generation_path_never_reads_the_test_year(conn, monkeypatch, fake_chat):
    """🔴🔴 **本计划最重要的一条** —— 防作弊。

    做法：把 `screen.candidates` 包一层，记下**生成阶段**发生的每一次数据库查询，
    然后断言：没有任何一次查询的参数里出现检验年。
    """
    rec = RecordingConn(conn)
    during_generation: list[tuple] = []
    original = screen.candidates

    def spy(c, cand, *, year, band=screen.BAND):
        rec.calls.clear()
        try:
            return original(c, cand, year=year, band=band)
        finally:
            during_generation.extend(rec.calls)

    monkeypatch.setattr("gaokao_audit.recommend.screen.candidates", spy)
    backtest.run(rec, fit_year=FIT, test_year=TEST, n_candidates=3, chat=fake_chat)

    assert during_generation, "没抓到任何生成阶段的查询 —— 测试本身失效了"
    for sql, params in during_generation:
        assert TEST not in params, (
            f"生成阶段读了检验年 {TEST}！这不是回测，是作弊。\nSQL: {sql}\n参数: {params}"
        )


def test_metrics_are_computed_on_the_test_year(conn, monkeypatch, fake_chat):
    """与上一条相反：**检验**必须用 test_year —— 那是回测允许且必须看的。"""
    seen: list[tuple] = []
    original = backtest._admitted

    def spy(*a, **k):
        seen.append(k.get("year"))
        return original(*a, **k)

    monkeypatch.setattr(backtest, "_admitted", spy)
    rep = backtest.run(conn, fit_year=FIT, test_year=TEST, n_candidates=3, chat=fake_chat)
    assert rep.details, "回测没产出任何细节"
    assert all(y == TEST for y in seen), f"检验阶段用的不是检验年：{set(seen)}"


def test_candidate_without_candidates_does_not_crash(conn, fake_chat):
    rep = backtest.run(conn, fit_year=FIT, test_year=TEST, n_candidates=1, chat=fake_chat)
    assert isinstance(rep.screened_out, int)


def test_report_shape(conn, fake_chat):
    rep = backtest.run(conn, fit_year=FIT, test_year=TEST, n_candidates=4, chat=fake_chat)
    assert 0.0 <= rep.admit_rate <= 1.0
    assert isinstance(rep.details, list) and rep.details
    # ⚠️ 「浪费分位」只有在**有人被录取**时才算得出 —— 一个人都没上时它是 None，
    #    那是诚实的结果（不可计算），不是 bug。这条断言把两者的关系锁住。
    assert (rep.waste_p50 is None) == (rep.admit_rate == 0.0), (
        "录取率与浪费分位对不上：有人上了却没有浪费分，或没人上却算出了浪费分"
    )
