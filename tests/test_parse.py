"""Task 2 · 截图 → 志愿表（4 处 LLM 调用之一）.

Review Focus 1：模型返回的不是合法 JSON / 缺字段 / 类型不对 —— 必须**降级并告知**，
不是崩溃、也不是拿一个空表继续往下跑。
"""
import json
from pathlib import Path

import pytest

from gaokao_audit.llm import client
from gaokao_audit.pipeline import parse

DEMO = Path(__file__).resolve().parents[1] / "assets" / "demo" / "probe.png"


def _vision_returning(text):
    return lambda *a, **k: text


def _payload(n=3):
    return {"items": [
        {"seq": i, "university_name": f"大学{i}", "major_group": f"{200 + i}",
         "min_score": 600 - i, "min_rank": 20000 + i, "tier": "稳"}
        for i in range(1, n + 1)
    ]}


# ── 走真 client（命中缓存，离线）──

@pytest.mark.skipif(not DEMO.is_file(), reason="探针截图不存在")
def test_parses_the_real_screenshot_offline():
    plan = parse.parse_screenshot(DEMO)
    assert len(plan.items) == 4
    assert plan.items[0].university_name == "暨南大学"
    assert plan.items[0].major_group == "201"
    assert plan.degraded is None


# ── 失败与边界 ──

def test_unparseable_output_degrades_instead_of_crashing():
    plan = parse.parse_screenshot(DEMO, vision=_vision_returning("这不是 JSON"))
    assert plan.items == []
    assert plan.degraded == "unparseable_output"


def test_json_wrapped_in_markdown_fence_is_accepted():
    """模型很爱把 JSON 包进 ```json 里 —— 这是常见形态，不是错误，要认。"""
    fenced = "```json\n" + json.dumps(_payload(2), ensure_ascii=False) + "\n```"
    plan = parse.parse_screenshot(DEMO, vision=_vision_returning(fenced))
    assert len(plan.items) == 2 and plan.degraded is None


def test_item_missing_required_field_degrades():
    """缺 university_name 的行不能当成有效条目 —— 否则后续检查会查一堆空字符串。"""
    bad = {"items": [{"seq": 1, "major_group": "201", "min_score": 600, "min_rank": 100, "tier": "稳"}]}
    plan = parse.parse_screenshot(DEMO, vision=_vision_returning(json.dumps(bad)))
    assert plan.items == []
    assert plan.degraded == "invalid_items"


def test_partial_item_is_kept_and_flagged_not_dropped():
    """某一行的分数读不出来 → **保留这一行**（专业组还在），只是那格为空。

    整行丢掉会让"我明明填了 30 条它只读到 27 条"这件事无从察觉。
    """
    partial = {"items": [
        {"seq": 1, "university_name": "甲大学", "major_group": "201",
         "min_score": None, "min_rank": None, "tier": "稳"},
        {"seq": 2, "university_name": "乙大学", "major_group": "202",
         "min_score": 600, "min_rank": 20000, "tier": "稳"},
    ]}
    plan = parse.parse_screenshot(DEMO, vision=_vision_returning(json.dumps(partial)))
    assert len(plan.items) == 2, "不该因为一个格子空就丢掉整行"
    assert plan.items[0].claimed_min_score is None


def test_raw_item_count_is_reported():
    """Review Focus 3 的根：把模型声称读到的行数记下来，供人工核对。"""
    plan = parse.parse_screenshot(DEMO, vision=_vision_returning(json.dumps(_payload(5))))
    assert plan.raw_item_count == 5


def test_model_returning_zero_items_degrades():
    plan = parse.parse_screenshot(DEMO, vision=_vision_returning('{"items": []}'))
    assert plan.items == [] and plan.degraded == "no_items"


def test_vision_failure_degrades():
    def boom(*a, **k):
        raise RuntimeError("DeepSeek 请求失败（URLError）")

    plan = parse.parse_screenshot(DEMO, vision=boom)
    assert plan.items == [] and plan.degraded == "vision_failed"
