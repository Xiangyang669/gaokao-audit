"""③ supervisor：要不要追加检查（4 处 LLM 调用之三）。

两条设计原则：

1. **能省掉就省掉** —— 没有任何问题时，**这一整次模型调用不该发生**。
   全系统只有 4 处 LLM 调用，这是其中唯一一处"经常能跳过"的。
   （这不是微优化：它同时让"没有问题"这条路径更快、更稳、更便宜。）

2. **追加动作是闭集** —— 模型只能从 `ACTIONS` 里选。
   开放式的"让它自己决定查什么"既不可测（没法写判据），又会让成本失控。
   模型编出来的名字一律**丢掉**，绝不真的去跑一个不存在的检查。

失败一律 = 不追加。追加本来就是锦上添花 —— Plan 1 的四个确定性检查已经把该报的都报了。
"""
import json
from typing import Callable, Iterable, Sequence

from gaokao_audit.llm import client, prompts
from gaokao_audit.models import Finding

ChatFn = Callable[..., str]

ACTIONS = ("adjacent_group_verify",)


def decide(findings: Sequence[Finding], *, chat: ChatFn | None = None) -> list[str]:
    if not findings:
        return []  # 🔴 先看有没有问题，再谈要不要花这次钱
    chat = chat or client.chat
    summary = _summarize(findings)
    try:
        raw = chat(
            [{"role": "user", "content": prompts.FOLLOWUP_PROMPT.replace("{Q}", summary)}],
            cache_key=f"followup:{summary}",
        )
    except Exception:  # noqa: BLE001 —— 决策失败 = 不追加，不往上抛
        return []
    return [a for a in _parse(raw) if a in ACTIONS]


def _summarize(findings: Iterable[Finding]) -> str:
    lines = [f"- 第 {f.seq} 条：{f.kind} —— {f.detail}" for f in findings]
    return "\n".join(lines) if lines else "（无）"


def _parse(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except Exception:  # noqa: BLE001
        return []
    if isinstance(data, dict):
        data = data.get("actions") or []
    if not isinstance(data, list):
        return []
    return [str(x) for x in data]
