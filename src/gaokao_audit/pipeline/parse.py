"""① 截图 → 志愿表。

**只做"把字读出来"**，不做任何判断 —— 判断是 Plan 1 那四个确定性检查的事。
这个边界守住了，模型出错的影响面就只限于"读错字"，而读错字是**可被人核对**的
（下一步就是人工确认）。

降级码：
  vision_failed     调用失败/超时
  unparseable_output 返回的不是合法 JSON
  no_items           JSON 合法但一条都没有
  invalid_items     有行缺了院校名或专业组号 —— 读得不完整，整份不可信，退回重来
"""
import json
import re
from pathlib import Path
from typing import Callable

from gaokao_audit.llm import client, prompts
from gaokao_audit.llm.schemas import ParsedItem, ParsedPlan

VisionFn = Callable[..., str]
_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")
_OBJECT = re.compile(r"\{.*\}", re.S)


def parse_screenshot(path: str | Path, *, vision: VisionFn | None = None) -> ParsedPlan:
    vision = vision or client.vision
    try:
        raw = vision(path, prompts.PARSE_PROMPT, cache_key=f"parse:{Path(path).name}")
    except Exception:  # noqa: BLE001 —— 调用失败是正常状态，落降级码
        return ParsedPlan([], 0, "vision_failed")

    data = _extract_json(raw)
    if data is None:
        return ParsedPlan([], 0, "unparseable_output")

    raw_items = data.get("items") or []
    if not raw_items:
        return ParsedPlan([], 0, "no_items")

    items: list[ParsedItem] = []
    complete = True
    for i, row in enumerate(raw_items, start=1):
        name = _text(row.get("university_name"))
        group = _norm_group(row.get("major_group"))
        if not name or not group:
            # 缺院校名或专业组号 = 这一行下游根本查不了；且说明模型读得不完整 → 整份不可信
            complete = False
            continue
        items.append(
            ParsedItem(
                seq=_int(row.get("seq")) or i,
                university_name=name,
                major_group=group,
                claimed_min_score=_int(row.get("min_score")),
                claimed_rank=_int(row.get("min_rank")),
                tier=_text(row.get("tier")) or None,
            )
        )

    if not complete or not items:
        return ParsedPlan([], len(raw_items), "invalid_items")
    return ParsedPlan(items, len(raw_items), None)


def _extract_json(text: str) -> dict | None:
    """模型爱把 JSON 包进 ```json 里 —— 那是常见形态，不是错误，要认。"""
    t = _FENCE.sub("", (text or "").strip())
    for candidate in (t, (_OBJECT.search(t).group(0) if _OBJECT.search(t) else None)):
        if not candidate:
            continue
        try:
            out = json.loads(candidate)
            if isinstance(out, dict):
                return out
        except Exception:  # noqa: BLE001
            continue
    return None


def _text(v) -> str:
    return "" if v is None else str(v).strip()


def _norm_group(v) -> str:
    """专业组号只留数字 —— 截图上常写成「（203）」。"""
    return re.sub(r"\D", "", _text(v))


def _int(v) -> int | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    digits = re.sub(r"\D", "", str(v))
    return int(digits) if digits else None
