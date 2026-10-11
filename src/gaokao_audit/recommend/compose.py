"""② LLM 排序组合 + 理由（**第 5 处 LLM 调用**）。

为什么这一处必须用模型：规则能做筛选与分档，但**做不了"这个人的偏好与哪些组更契合"**，
更写不出"为什么推荐它给他"。**它做的是规则做不到的事，所以值得花这次钱。**

🔴 但模型只在**已筛出的候选**里挑 —— 它不许发明。候选之外的名字一律丢掉（Review Focus 4）。
"""
import json
import re
from typing import Callable

from gaokao_audit.llm import client, prompts
from gaokao_audit.recommend.models import Candidate, Group, Recommendation

ChatFn = Callable[..., str]
DEFAULT_N = 30
_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")
_OBJECT = re.compile(r"\{.*\}", re.S)


def recommend(
    cand: Candidate, groups: list[Group], *, n: int = DEFAULT_N, chat: ChatFn | None = None
) -> list[Recommendation]:
    if not groups:
        return []   # 没候选就别调模型 —— 它只能编
    chat = chat or client.chat
    listing = json.dumps(
        [
            {"university_name": g.university_name, "major_group": g.major_group,
             "min_score": g.min_score, "min_rank": g.min_rank, "subject_req": g.subject_req}
            for g in groups
        ],
        ensure_ascii=False,
    )
    prompt = (
        prompts.RECOMMEND_PROMPT
        .replace("{N}", str(n))
        .replace("{SCORE}", str(cand.score))
        .replace("{CATEGORY}", cand.category)
        .replace("{RANK}", str(cand.rank))
        .replace("{SUBJECTS}", "/".join(cand.subjects) or "（未提供）")
        .replace("{CITIES}", "/".join(cand.cities) or "无偏好")
        .replace("{MAJORS}", "/".join(cand.majors) or "无偏好")
        .replace("{G}", listing)
    )
    try:
        raw = chat([{"role": "user", "content": prompt}],
                   cache_key=f"recommend:{cand}:{n}:{listing[:2000]}")
    except Exception:  # noqa: BLE001
        return []

    data = _extract_json(raw)
    if not data:
        return []
    return _filter(data.get("recommendations") or [], groups, n)


def _filter(rows: list, groups: list[Group], n: int) -> list[Recommendation]:
    allowed = {(g.university_name, g.major_group) for g in groups}
    out: list[Recommendation] = []
    seen: set[tuple[str, str]] = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        key = (str(r.get("university_name", "")).strip(), str(r.get("major_group", "")).strip())
        if key not in allowed or key in seen:
            continue                      # 不在候选里（模型编的）或重复
        reason = str(r.get("reason", "")).strip()
        if not reason:
            continue                      # 空理由不算数 —— 说得出为什么才有价值
        out.append(Recommendation(key[0], key[1], str(r.get("tier") or "稳").strip(), reason))
        seen.add(key)
        if len(out) >= n:
            break
    return out


def _extract_json(text: str) -> dict | None:
    t = _FENCE.sub("", (text or "").strip())
    m = _OBJECT.search(t)
    for candidate in (t, m.group(0) if m else None):
        if not candidate:
            continue
        try:
            out = json.loads(candidate)
            if isinstance(out, dict):
                return out
        except Exception:  # noqa: BLE001
            continue
    return None
