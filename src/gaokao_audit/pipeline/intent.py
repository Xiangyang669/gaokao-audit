"""② 提问 → 意图（4 处 LLM 调用之二）。

**这一处的定位是"入口级"的** —— 它炸了整条链路就炸了。
所以它有一个硬约束：**任何输入、任何失败都不许抛异常**，一律落到 `full_check`。
分类错了顶多审得宽一点；链路断了才是真事故。
"""
import json
from typing import Callable

from gaokao_audit.llm import client, prompts
from gaokao_audit.llm.schemas import Intent

ChatFn = Callable[..., str]


def classify(question: str, *, chat: ChatFn | None = None) -> Intent:
    chat = chat or client.chat
    try:
        raw = chat(
            [{"role": "user", "content": prompts.INTENT_PROMPT.replace("{Q}", question or "")}],
            cache_key=f"intent:{question}",
        )
    except Exception:  # noqa: BLE001 —— 入口级：失败必须兜住，不能往上抛
        return Intent.full_check
    return _parse(raw)


def _parse(raw: str) -> Intent:
    """模型可能只回标签、回 JSON、或回带前缀的一段话 —— 三种都认。"""
    text = (raw or "").strip().lower()
    if not text:
        return Intent.full_check
    try:
        data = json.loads(text)
        if isinstance(data, dict) and isinstance(data.get("intent"), str):
            text = data["intent"].strip().lower()
    except Exception:  # noqa: BLE001 —— 不是 JSON 很正常，继续按纯文本找
        pass
    for candidate in Intent:
        if candidate.value in text:
            return candidate
    return Intent.full_check
