"""Task 7 · FastAPI 服务 + 成本护栏.

这是**唯一直接对着钱的一层**。三条硬要求：
  ① **配额在调模型之前扣** —— 事后扣意味着"钱已经花了才记账"，挡不住刷
  ② **超配额转演示模式，不报错** —— 访客看到的是"看演示"，不是 500
  ③ **异常绝不外泄** —— 尤其不能把 traceback 返回给前端（traceback 里可能有内部路径）
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest_helpers import make_ctx, make_items
from gaokao_audit.api import main as api

DEMO = Path(__file__).resolve().parents[1] / "assets" / "demo" / "probe.png"


class FakeChat:
    def __init__(self, report=None):
        self.report = report
        self.calls = 0

    def __call__(self, messages, **kw):
        import re

        self.calls += 1
        content = messages[0]["content"] if isinstance(messages, list) else str(messages)
        if "stability" in content and "reachability" in content:
            return "full_check"
        if "adjacent_group_verify" in content and "actions" in content:
            return json.dumps({"actions": []})
        if self.report is not None:
            return self.report
        seqs = sorted({int(m) for m in re.findall(r'"seq"\s*:\s*(\d+)', content)})
        return "".join(f"第 {n} 条 有问题。" for n in seqs) or "没有发现问题。"


@pytest.fixture
def client(conn):
    app = api.create_app(conn=conn, guard=api.Guard(per_ip_daily=3), chat=FakeChat())
    return TestClient(app, raise_server_exceptions=False)


def _payload(**kw):
    p = {
        "question": "这表稳不稳",
        "category": "物理类",
        "year": 2025,
        "candidate_rank": 20000,
        "candidate_subjects": ["物理", "化学", "生物"],
        "items": [
            {"seq": 1, "university_name": "某大学", "major_group": "201",
             "claimed_min_score": 600, "claimed_rank": 20000, "tier": "稳"}
        ],
    }
    p.update(kw)
    return p


def test_healthz(client):
    assert client.get("/healthz").json()["status"] == "ok"


def test_parse_exposes_the_item_count_for_human_check(client):
    """Review Focus 3：读到的行数必须显示出来 —— 人才能发现"少读了几行"。"""
    with DEMO.open("rb") as f:
        r = client.post("/parse", files={"file": ("probe.png", f, "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["raw_item_count"] == 4
    assert len(body["items"]) == 4
    assert body["degraded"] is None


def test_confirm_returns_findings_and_narrative(client):
    r = client.post("/confirm", json=_payload())
    assert r.status_code == 200
    body = r.json()
    assert "findings" in body and "narrative" in body
    assert body["mode"] == "live"


# ── 护栏 ──

def test_over_ip_quota_falls_back_to_demo_mode_not_error(client):
    for _ in range(3):
        assert client.post("/confirm", json=_payload()).json()["mode"] == "live"
    r = client.post("/confirm", json=_payload())
    assert r.status_code == 200, "超配额不能报错"
    assert r.json()["mode"] == "demo"
    assert r.json()["reason"] == "ip_quota"


def test_over_quota_does_not_call_the_model(conn):
    """🔴 真正要防的是钱：超配额时**一次模型调用都不该发生**。"""
    fake = FakeChat()
    app = api.create_app(conn=conn, guard=api.Guard(per_ip_daily=2), chat=fake)
    c = TestClient(app, raise_server_exceptions=False)
    for _ in range(2):
        c.post("/confirm", json=_payload())
    before = fake.calls
    assert c.post("/confirm", json=_payload()).json()["mode"] == "demo"
    assert fake.calls == before, "超配额了还在调模型 —— 配额形同虚设"


def test_quota_is_consumed_even_when_the_call_fails(conn, monkeypatch):
    """🔴 **先扣后调**的直接证据：调用失败也照样扣掉了配额。

    如果反过来（先调后扣），失败路径就不扣 —— 刷的人只要让调用失败就能免费用。
    """
    from gaokao_audit.pipeline import flow

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(flow, "build", boom)
    app = api.create_app(conn=conn, guard=api.Guard(per_ip_daily=2), chat=FakeChat())
    c = TestClient(app, raise_server_exceptions=False)
    for _ in range(2):
        assert c.post("/confirm", json=_payload()).status_code == 500
    # 两次都 consumed 了 → 第三次该是演示模式
    assert c.post("/confirm", json=_payload()).json()["mode"] == "demo"


def test_global_cost_cap_triggers_demo_mode(conn):
    """封顶设成"正好够一次" —— 第二次就该被拦。

    ⚠️ 注意：封顶若小于单次成本，**第一次就该拦**（否则必然超支）。
    所以这里用的是 0.03（单次 0.02），不是 0.01。
    """
    app = api.create_app(
        conn=conn, guard=api.Guard(per_ip_daily=99, global_cap_yuan=0.03), chat=FakeChat()
    )
    c = TestClient(app, raise_server_exceptions=False)
    assert c.post("/confirm", json=_payload()).json()["mode"] == "live"
    r = c.post("/confirm", json=_payload()).json()
    assert r["mode"] == "demo" and r["reason"] == "global_cap"


def test_cap_below_one_request_blocks_immediately(conn):
    """封顶比单次成本还低 → 一次都不放行。允许一次就等于必然超支。"""
    app = api.create_app(
        conn=conn, guard=api.Guard(per_ip_daily=99, global_cap_yuan=0.001), chat=FakeChat()
    )
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/confirm", json=_payload()).json()
    assert r["mode"] == "demo" and r["reason"] == "global_cap"


# ── 异常不外泄 ──

def test_traceback_is_never_returned_to_the_client(conn, monkeypatch):
    """🔴 这是**安全措施**，不只是工程规范：traceback 里可能有内部路径。"""
    from gaokao_audit.pipeline import flow

    def boom(*a, **k):
        raise RuntimeError("内部实现细节 / 不应该给外面看")

    monkeypatch.setattr(flow, "build", boom)
    app = api.create_app(conn=conn, guard=api.Guard(), chat=FakeChat())
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/confirm", json=_payload())
    assert r.status_code == 500
    text = r.text
    assert "Traceback" not in text
    assert "内部实现细节" not in text
    assert "gaokao_audit" not in text
    assert r.json()["error"], "要给一个结构化的错误，不能什么都不说"


def test_demo_endpoint_never_fails(client):
    assert client.get("/demo").status_code == 200


def test_example_endpoint_gives_a_ready_to_use_plan(client):
    """面试官点开网站时手上没有截图 —— 「载入示例」必须能给出完整一张表。"""
    body = client.get("/example").json()
    assert body["items"], "示例表是空的 —— 点开会什么都看不到"
    assert body["raw_item_count"] == len(body["items"])
    assert body["question"]


def test_confirm_produces_real_findings_not_checker_failed(conn):
    """🔴 回归护栏（踩过三次的坑）：FastAPI 的同步端点跑在**线程池**里。

    共享一条在主线程创建的 sqlite 连接 → 四个检查全抛
    `ProgrammingError: SQLite objects created in a thread can only be used in that same thread`；
    而 audit.run 会把异常吞成 checker_failed，表现成
    「四个检查全崩、一条发现都没有」—— 极难往线程上想。

    这条用**真表**跑完整链路，断言拿到的是真发现，而不是一路 checker_failed。
    """
    from conftest_helpers import make_ctx, make_items
    from gaokao_audit.models import PlanItem

    ctx = make_ctx()
    clean = make_items(conn, n=3)
    reachless = conn.execute(
        "select university_name, major_group, min_score from admission_line "
        "where year=2025 and category=? and min_rank < ? limit 1",
        (ctx.category, ctx.candidate_rank),
    ).fetchone()
    bad = PlanItem(seq=99, university_name=reachless[0], major_group=reachless[1],
                   claimed_min_score=int(reachless[2]), claimed_rank=1, subject_req=None, tier="稳")
    app = api.create_app(conn=conn, guard=api.Guard(per_ip_daily=9), chat=FakeChat())
    c = TestClient(app, raise_server_exceptions=False)

    body = c.post("/confirm", json=_payload(items=[vars(i) for i in clean + [bad]])).json()
    assert not any("checker_failed" in v for v in body["degraded"].values()), (
        f"检查整路崩了 —— 大概率又是 SQLite 跨线程：{body['degraded']}"
    )
    assert len(body["outcomes"]) == 4, f"四路检查没跑全：{body['outcomes']}"
    assert body["findings"], "有问题的表却没报出任何发现"


# ── A2A（Task 2）──

CARD_PATH = "/.well-known/agent-card.json"
RPC = "/a2a"


def _rpc_body(payload: dict, msg_id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "method": "message/send",
            "params": {"message": {"role": "user", "messageId": "m1",
                                   "parts": [{"kind": "text", "text": json.dumps(payload)}]}}}


def test_agent_card_is_served_at_the_well_known_path(client):
    r = client.get(CARD_PATH)
    assert r.status_code == 200
    card = r.json()
    assert card["skills"][0]["id"] == "check_volunteer_plan"
    assert card["url"].endswith(RPC)


def test_card_declares_the_input_contract(client):
    """外部 agent 照着 card 调用，得知道该塞什么进去。"""
    contract = client.get(CARD_PATH).json()["skills"][0]["input_contract"]
    assert "items" in contract and "question" in contract


def test_a2a_message_send_returns_an_agent_message(conn):
    app = api.create_app(conn=conn, guard=api.Guard(per_ip_daily=9), chat=FakeChat())
    c = TestClient(app, raise_server_exceptions=False)
    body = c.post(RPC, json=_rpc_body(_payload())).json()
    assert body["jsonrpc"] == "2.0"
    assert body["result"]["role"] == "agent"
    assert body["result"]["parts"][0]["text"]


def test_a2a_entry_consumes_the_same_quota_as_confirm(conn):
    """🔴 Review Focus 2：A2A 是一个**新的、更隐蔽的入口**。

    忘了接护栏 = 给钱包开了个后门：访客绕开 /confirm 的限流，
    直接从 A2A 反复调用。这条测试就是盯着这个后门。
    """
    app = api.create_app(conn=conn, guard=api.Guard(per_ip_daily=1), chat=FakeChat())
    c = TestClient(app, raise_server_exceptions=False)

    assert c.post("/confirm", json=_payload()).json()["mode"] == "live"   # 用掉唯一一次
    r = c.post(RPC, json=_rpc_body(_payload())).json()
    text = r["result"]["parts"][0]["text"]
    assert "演示模式" in text, f"A2A 绕过了配额：{text[:120]}"


def test_a2a_unknown_method_returns_jsonrpc_error_not_fake_success(client):
    r = client.post(RPC, json={"jsonrpc": "2.0", "id": 9, "method": "tasks/get"}).json()
    assert r["error"]["code"] == -32601


def test_a2a_non_json_text_is_explained_not_crashed(client):
    body = {"jsonrpc": "2.0", "id": 2, "method": "message/send",
            "params": {"message": {"role": "user", "messageId": "m", "parts": [{"kind": "text", "text": "随便说句话"}]}}}
    r = client.post(RPC, json=body).json()
    assert "契约" in r["result"]["parts"][0]["text"]


def test_a2a_parse_error_is_structured(client):
    r = client.post(RPC, content="不是 json", headers={"Content-Type": "application/json"}).json()
    assert r["error"]["code"] == -32700


# ── 推荐（Plan 4）──

def test_recommend_consumes_the_same_quota_as_every_other_entry(conn):
    """🔴 /recommend 是**又一个新入口** —— 它也会调模型，忘了接护栏就是后门。"""
    app = api.create_app(conn=conn, guard=api.Guard(per_ip_daily=1), chat=FakeChat())
    c = TestClient(app, raise_server_exceptions=False)
    payload = {"score": 600, "category": "物理类", "rank": 20000, "year": 2025,
               "subjects": ["物理", "化学", "生物"], "cities": ["广州"], "majors": ["计算机"]}
    assert c.post("/recommend", json=payload).json()["mode"] == "live"
    assert c.post("/recommend", json=payload).json()["mode"] == "demo"


def test_recommend_returns_recommendations_and_self_audit(conn):
    app = api.create_app(conn=conn, guard=api.Guard(per_ip_daily=9), chat=FakeChat())
    c = TestClient(app, raise_server_exceptions=False)
    body = c.post("/recommend", json={"score": 600, "category": "物理类", "rank": 20000,
                                      "year": 2025, "subjects": ["物理", "化学", "生物"]}).json()
    assert body["mode"] == "live"
    assert "recommendations" in body and "findings" in body   # 自审结论一并返回
