"""FastAPI 服务：三个端点 + 统一异常处理.

- `POST /parse`    上传截图 → **待确认**的条目（人工确认这一步的输入）
- `POST /confirm`  确认后的条目 + 提问 → 报告（HITL 的第二步）
- `GET  /demo`     预生成报告（配额用完时降级到这里）
- `GET  /healthz`

🔴 **异常一律不外泄**：这是安全措施，不只是工程规范 ——
traceback 会把内部路径、模块名、甚至调用链暴露给任何访客。
"""
import json
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import JSONResponse

from gaokao_audit.api import a2a
from gaokao_audit.api.guard import Guard
from gaokao_audit.models import AuditContext, PlanItem
from gaokao_audit.pipeline import flow, parse

_ASSETS = Path(__file__).resolve().parents[3] / "assets" / "demo"
DEMO_REPORT = _ASSETS / "report.md"
DEMO_SHOT = _ASSETS / "screenshot.png"       # Task 9 产出；没有就退回探针图
DEMO_FALLBACK_SHOT = _ASSETS / "probe.png"
DEMO_QUESTION = "我这表稳不稳，会不会滑档？"
_GENERIC_ERROR = "服务内部错误，已记录。请稍后重试。"


def create_app(*, conn=None, conn_factory=None, guard: Guard | None = None, chat=None) -> FastAPI:
    """`conn_factory` 优先：**每个请求现开一条连接**，用完就关。

    为什么是工厂而不是一条共享连接：同步端点跑在线程池里，共享连接会撞上
    SQLite 的线程检查（见 db.connect 的注释）。给 `conn` 也行，但那只适合测试。
    """
    if conn is None and conn_factory is None:
        raise ValueError("必须给 conn 或 conn_factory 之一")
    guard = guard or Guard()

    def _conn():
        return conn_factory() if conn_factory else conn

    app = FastAPI(title="gaokao-audit", description="高考志愿方案审计器")

    # 兜底：任何没被下面捕获的异常，都变成结构化错误，绝不带 traceback 出去
    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):  # noqa: ARG001
        return JSONResponse(status_code=500, content={"error": _GENERIC_ERROR})

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "spent_yuan": guard.spent_yuan}

    @app.get("/demo")
    def demo() -> dict:
        text = DEMO_REPORT.read_text(encoding="utf-8") if DEMO_REPORT.is_file() else ""
        return {"mode": "demo", "narrative": text, "degraded": None if text else "demo_missing"}

    @app.get("/example")
    def example() -> dict:
        """给前端「载入示例」用：一张已经解析好的表 + 一句示例提问。

        面试官点开就能看到完整效果 —— 否则他手上没有截图，什么都看不到。
        解析结果在缓存里，所以这一步**离线也能跑**。
        """
        shot = DEMO_SHOT if DEMO_SHOT.is_file() else DEMO_FALLBACK_SHOT
        parsed = parse.parse_screenshot(shot)
        return {
            "items": [vars(i) for i in parsed.items],
            "raw_item_count": parsed.raw_item_count,
            "question": DEMO_QUESTION,
            "degraded": parsed.degraded,
        }

    @app.post("/parse")
    async def parse_endpoint(file: UploadFile = File(...)) -> dict:
        suffix = Path(file.filename or "shot.png").suffix or ".png"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            path = Path(tmp.name)
        try:
            # 🔴 解析**不扣配额**：它不花模型钱吗？花。但它是"还没出结果"的一步，
            # 扣在 /confirm 更合理（用户可能改完就不提交了）。这里如实返回 degraded。
            # 走真 client（截图解析结果在 llm_cache 里，测试与演示都离线可复现）
            plan = parse.parse_screenshot(path)
        finally:
            path.unlink(missing_ok=True)
        return {
            "items": [vars(i) for i in plan.items],
            "raw_item_count": plan.raw_item_count,   # Review Focus 3：行数给人核对
            "degraded": plan.degraded,
        }

    def _audit_from_payload(payload: dict, ip: str | None) -> JSONResponse:
        """**唯一**的审计入口 —— `/confirm` 与 A2A 都走这里，所以护栏无法被绕过。"""
        verdict = guard.check_and_consume(ip)
        if not verdict.allowed:
            return JSONResponse(_demo_body(verdict.reason))
        try:
            ctx = AuditContext(
                year=int(payload.get("year", 2025)),
                category=str(payload.get("category", "")),
                candidate_rank=_opt_int(payload.get("candidate_rank")),
                candidate_subjects=tuple(payload.get("candidate_subjects") or ()),
            )
            items = [_to_item(i) for i in payload.get("items", [])]
            rep = flow.build(items, str(payload.get("question", "")), _conn(), ctx, chat=chat)
        except Exception:  # noqa: BLE001 —— 绝不外泄，也不带 traceback
            return JSONResponse(status_code=500, content={"error": _GENERIC_ERROR})
        return JSONResponse(
            {
                "mode": "live",
                "intent": rep.intent.value,
                "findings": [vars(f) for f in rep.findings],
                "narrative": rep.narrative,
                "outcomes": rep.outcomes,
                "degraded": rep.degraded,
            }
        )

    @app.post("/recommend")
    def recommend(payload: dict, request: Request) -> JSONResponse:
        """推荐生成 —— **与 /confirm 走同一套配额**（它同样会调模型）。"""
        verdict = guard.check_and_consume(request.client.host if request.client else None)
        if not verdict.allowed:
            return JSONResponse(_demo_body(verdict.reason))
        try:
            from gaokao_audit.recommend import flow as rec_flow
            from gaokao_audit.recommend.models import Candidate

            cand = Candidate(
                score=int(payload.get("score", 0)),
                category=str(payload.get("category", "")),
                rank=int(payload.get("rank", 0)),
                subjects=tuple(payload.get("subjects") or ()),
                cities=tuple(payload.get("cities") or ()),
                majors=tuple(payload.get("majors") or ()),
            )
            rep = rec_flow.build(cand, _conn(), year=int(payload.get("year", 2025)),
                                 n=int(payload.get("n", 8)), chat=chat)
        except Exception:  # noqa: BLE001
            return JSONResponse(status_code=500, content={"error": _GENERIC_ERROR})
        return JSONResponse({
            "mode": "live",
            "recommendations": [vars(r) for r in rep.recommendations],
            "findings": [vars(f) for f in rep.findings],   # 自审结论
            "outcomes": rep.outcomes,
            "degraded": rep.degraded,
        })

    @app.post("/confirm")
    def confirm(payload: dict, request: Request) -> JSONResponse:
        return _audit_from_payload(payload, request.client.host if request.client else None)

    async def _a2a_run(text: str, ip: str | None) -> str:
        """A2A 的 message/send 里，text 是一份 JSON 契约（见 agent card 的 input_contract）。"""
        try:
            payload = json.loads(text)
        except Exception:  # noqa: BLE001
            return ("输入不是合法 JSON。本 agent 的输入契约见 "
                    "/.well-known/agent-card.json 的 skills[0].input_contract。")
        body = _audit_from_payload(payload, ip).body
        data = json.loads(body)
        if data.get("mode") == "demo":
            head = f"[演示模式：{data.get('reason')}]"
            return "\n\n".join([head, data.get("narrative") or ""])
        if data.get("narrative"):
            return data["narrative"]
        lines = [f"第 {f['seq']} 条 {f['kind']}：{f['detail']}" for f in data.get("findings", [])]
        return "\n".join(lines) or "未发现问题。"

    a2a.mount(app, base_url=os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:8000"),
              run=_a2a_run)

    return app


def _demo_body(reason: str | None) -> dict:
    text = DEMO_REPORT.read_text(encoding="utf-8") if DEMO_REPORT.is_file() else ""
    return {"mode": "demo", "reason": reason, "narrative": text,
            "findings": [], "degraded": None if text else "demo_missing"}


def _to_item(row: dict) -> PlanItem:
    return PlanItem(
        seq=int(row.get("seq", 0)),
        university_name=str(row.get("university_name", "")),
        major_group=str(row.get("major_group", "")),
        claimed_min_score=_opt_int(row.get("claimed_min_score")),
        claimed_rank=_opt_int(row.get("claimed_rank")),
        subject_req=row.get("subject_req"),
        tier=str(row.get("tier") or "稳"),
    )


def _opt_int(v) -> int | None:
    try:
        return int(v) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


