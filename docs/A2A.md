# A2A：只对外，且不手搓协议 —— 但也没接官方 SDK

## 一句话

本系统以 A2A **对外**暴露成一个可被发现、可被调用的 agent：
`GET /.well-known/agent-card.json` 给出 Agent Card，`POST /a2a` 收 JSON-RPC 2.0。

## 🔴 取舍一：**只对外，内部不用 A2A**

内部那些检查共享同一张图和内存。套上 A2A，等于**把内存里直接传的东西序列化成 HTTP 再解回来**。

> **A2A 的定位是跨系统，不是进程内通信。**

所以它只做一件事：让**外部** agent 按标准发现我们、调用我们。

## 🔴 取舍二：**没接官方 SDK**（`a2a-sdk` 1.2.2）

**试过，放弃了 —— 理由是成本不可估，不是"懒得接"：**

- `AgentCard` 是 **protobuf 消息**（`google._upb`），不是 dataclass/pydantic 模型；
  网上教程里的 JSON 风格 API 已经不存在了
- 请求处理器**并存** `DefaultRequestHandler` 与 **`LegacyRequestHandler`** ——
  名字里带 Legacy 的那个是旧 API，说明 SDK 正在换代
- `a2a.utils` 里**连"造一条文本消息"的 helper 都没有**（教程里的 `new_agent_text_message` 已删），
  得自己拼 `a2a_pb2.Message` 再塞进 `EventQueue`

**每探一步就冒出一个新缺口。**

而 A2A 规范把线上格式定义得很清楚：**一份 JSON 文档（Agent Card）** + **JSON-RPC 2.0 的 `message/send`**。
产出这两种格式**不是"手搓协议"，是产出规范定义的东西**。

### 代价（如实说）

因此**不支持**：
- 流式（`message/stream`）
- 任务推送（push notifications）
- **签名 Agent Card**（JWS）
- 与新协议版本的自动协商

这些都是用 SDK 才拿得到的东西。**本实现覆盖的是 discovery + 单次调用这两个最核心的部分。**

## 🔴 取舍三：**它和 `/confirm` 走同一套配额**

A2A 是一个**新的、更隐蔽的入口** —— 访客不需要偷 key，绕开 `/confirm` 的限流反复调 A2A，
就在花你的钱。所以两个入口共用同一个 `guard.check_and_consume`，
`/a2a` 的处理函数里**不自己跑审计**，而是调用注入进来的同一条路径。

**有专门的测试盯着这个后门**（`test_a2a_entry_consumes_the_same_quota_as_confirm`）。

## 输入契约

`message.parts[0].text` 必须是一份 JSON（形状写在 Agent Card 的 `skills[0].input_contract` 里）：

```json
{
  "question": "我这表稳不稳？",
  "category": "物理类", "year": 2025,
  "candidate_rank": 20000, "candidate_subjects": ["物理","化学","生物"],
  "items": [{"seq":1,"university_name":"暨南大学","major_group":"201",
             "claimed_min_score":612,"claimed_rank":18043,"tier":"稳"}]
}
```

**为什么是 JSON 而不是自然语言**：审计需要结构化的表，而模型的截图解析在**上一层**
（`/parse` + 人工确认）。A2A 是一个**机器对机器**的接口，不该再让对面去猜格式。
