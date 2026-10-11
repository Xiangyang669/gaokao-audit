"""④ 检查结果 → 人话报告（4 处 LLM 调用之四）。

**这一处是"锦上添花"层**：它只负责把已经确定的结构化结论转述成人话。
所以它的失败**绝不能**影响结论 —— 失败就返回空串，由上层标 `narrative_failed`，
结构化 findings 原样交出去。

⚠️ **漏条的报告一律作废**（返回空串）：
一份"看起来完整、其实漏了两条"的散文，比直接给结构化清单**更危险** ——
用户会以为只有一处问题。宁可退回结构化结果。
"""
import json
from typing import Callable, Sequence

from gaokao_audit.llm import client, prompts
from gaokao_audit.models import Finding

ChatFn = Callable[..., str]


def render(findings: Sequence[Finding], question: str, *, chat: ChatFn | None = None) -> str:
    chat = chat or client.chat
    listing = _listing(findings)
    try:
        raw = chat(
            [{"role": "user", "content": prompts.REPORT_PROMPT.replace("{Q}", question or "")
              .replace("{L}", listing)}],
            cache_key=f"report:{question}:{listing}",
        )
    except Exception:  # noqa: BLE001 —— 散文没了，结论不能没
        return ""

    text = (raw or "").strip()
    if not text:
        return ""
    if not _covers(text, findings):
        return ""  # 漏条 → 作废，交由上层降级
    return text


def _listing(findings: Sequence[Finding]) -> str:
    if not findings:
        return "（本次检查没有发现问题）"
    return json.dumps(
        [
            {
                "seq": f.seq, "kind": f.kind, "detail": f.detail,
                "claimed": f.claimed, "actual": f.actual, "evidence": f.evidence,
            }
            for f in findings
        ],
        ensure_ascii=False,
        indent=1,
    )


def _covers(text: str, findings: Sequence[Finding]) -> bool:
    """报告必须提到每一条的序号。

    只认「第 N 条」这个格式 —— 光找数字太松（"1" 会命中"18043"）。
    """
    return all(f"第 {f.seq} 条" in text for f in findings)
