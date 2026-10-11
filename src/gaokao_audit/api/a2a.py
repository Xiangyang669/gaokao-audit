"""A2A（Agent2Agent）：把本系统**对外**暴露成一个可被发现、可被调用的 agent。

**为什么只对外**（spec §7 的取舍，面试要能讲）：
内部那些检查共享同一张图和内存，套上 A2A 只是把内存里的东西序列化成 HTTP 再解回来。
**A2A 的定位是跨系统，不是进程内通信。** 所以只用它做一件事：
让**外部** agent 按标准发现我们、调用我们。

🔴 A2A 是一个**新的入口** —— 它必须和 `/confirm` 走**同一套配额**。
忘了接护栏，等于给钱包开一个后门（Review Focus 2）。所以这里**不自己跑审计**，
而是调用 `api/main.py` 注入进来的 `run_confirmed`（那条路径上有配额）。

---

## 为什么没接官方 SDK（`a2a-sdk` 1.2.2）

试过，放弃了 —— 理由是**成本不可估**，不是"懒得接"：

- `AgentCard` 是 **protobuf 消息**（`google._upb`），不是 dataclass/pydantic 模型，
  和网上教程里的 JSON 风格完全不是一回事
- 请求处理器是 **`DefaultRequestHandler` 与 `LegacyRequestHandler` 并存**，名字里带 Legacy
  的那个是旧 API —— 说明 SDK 正在换代
- `a2a.utils` 里**连"造一条文本消息"的 helper 都没有**（教程里的 `new_agent_text_message` 已不存在），
  要自己拼 `a2a_pb2.Message` 再塞进 `EventQueue`

**每探一步就冒出一个新缺口**，接通的轮次无法预估。而 A2A 规范把线上格式定义得很清楚：
**一份 JSON 文档（Agent Card）+ JSON-RPC 2.0 的 `message/send`**。
产出这两种格式**不是"手搓协议"，是产出规范定义的东西**。

**代价（如实说）**：因此**不支持**流式（`message/stream`）、任务推送、签名 card、
以及与后续协议版本的自动协商。这些都是用 SDK 才拿得到的东西。
"""
from __future__ import annotations

import uuid
from typing import Any, Awaitable, Callable

# ⚠️ 必须**在模块层**导入。本文件有 `from __future__ import annotations`，
# 函数签名里的注记是**字符串**，FastAPI 要到模块全局去解析它 ——
# 导在函数内部的话它解析不到 `Request`，会把它当成 query 参数，
# 表现成 422 `{"loc":["query","request"],"msg":"Field required"}`。
from fastapi import Request
from fastapi.responses import JSONResponse

SKILL_ID = "check_volunteer_plan"
RPC_URL = "/a2a"
CARD_PATH = "/.well-known/agent-card.json"
PROTOCOL_VERSION = "1.0"

_CARD_DESCRIPTION = (
    "高考志愿方案**审计器**。检查一份志愿表里的数据与逻辑是否自洽，给出带证据的问题清单。"
    "**它只审计、不推荐** —— 不回答「你该怎么填」。"
)
_SKILL_DESCRIPTION = (
    "输入一份志愿表（若干「院校 + 专业组 + 声称的最低分/最低位次/档位」）与一个提问，"
    "返回该表里**依据对不上**的条目及其证据。**不生成志愿方案、不做录取预测。**"
)


def agent_card(base_url: str) -> dict[str, Any]:
    """Agent Card —— 就是 `/.well-known/agent-card.json` 返回的那份 JSON 文档。

    ⚠️ 边界必须写进 card：外部 agent 照着 card 调用，不能以为它能出志愿方案。
    """
    base = base_url.rstrip("/")
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "name": "gaokao-audit",
        "description": _CARD_DESCRIPTION,
        "url": f"{base}{RPC_URL}",
        "version": "1.0.0",
        "capabilities": {"streaming": False},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [
            {
                "id": SKILL_ID,
                "name": "审计一份高考志愿表",
                "input_contract": (
                    "message.parts[0].text 必须是一个 JSON 文档，形状："
                    '{"question": str, "category": str, "year": int, '
                    '"candidate_rank": int, "candidate_subjects": [str], '
                    '"items": [{"seq": int, "university_name": str, "major_group": str, '
                    '"claimed_min_score": int, "claimed_rank": int, "tier": str}]}'
                ),
                "description": _SKILL_DESCRIPTION,
                "tags": ["education", "audit", "gaokao"],
                "examples": ["我这表稳不稳，会不会滑档？", "我能不能上暨南大学？"],
            }
        ],
    }


def _text_of(params: dict) -> str:
    parts = ((params or {}).get("message") or {}).get("parts") or []
    return " ".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()


def _agent_message(text: str) -> dict:
    return {
        "kind": "message",
        "role": "agent",
        "messageId": uuid.uuid4().hex,
        "parts": [{"kind": "text", "text": text}],
    }


async def handle_jsonrpc(body: Any, run: Callable[[str, str | None], Awaitable[str]],
                         ip: str | None = None) -> dict:
    """把一次 JSON-RPC 请求翻译成一次审计。

    ⚠️ 刻意**只支持 `message/send`** —— 不支持的方法明确回 -32601，不假装成功。
    """
    rid = (body or {}).get("id")
    method = (body or {}).get("method")

    if method != "message/send":
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601,
                          "message": f"不支持的方法：{method}（本 agent 只提供 message/send）"}}

    text = _text_of((body or {}).get("params") or {})
    if not text:
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32602, "message": "params.message.parts 里没有文本"}}

    try:
        reply = await run(text, ip)
    except Exception:  # noqa: BLE001 —— 协议层失败也要给结构化错误，不能裸抛
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32603, "message": "审计服务内部错误，已记录。"}}

    return {"jsonrpc": "2.0", "id": rid, "result": _agent_message(reply)}


def mount(app, *, base_url: str, run: Callable[[str, str | None], Awaitable[str]]) -> None:
    """把 A2A 的两个线上端点挂到已有的 FastAPI 上。

    `run` 由 `api/main.py` 注入 —— 它**复用** `/confirm` 那条路径（含配额），
    所以 A2A 不可能绕过护栏（Review Focus 2）。
    """
    @app.get(CARD_PATH)
    def _card() -> dict:
        return agent_card(base_url)

    @app.post(RPC_URL)
    async def _rpc(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return JSONResponse({"jsonrpc": "2.0", "id": None,
                                 "error": {"code": -32700, "message": "请求体不是合法 JSON"}})
        ip = request.client.host if request.client else None
        return JSONResponse(await handle_jsonrpc(body, run, ip))
