"""起服务： py scripts/serve.py  （默认 127.0.0.1:8000）

⚠️ 默认只听本机。要对外，必须先把 guard 的配额设成真实值 ——
   公开一个会调模型的接口而不设配额，等于把自己的钱包挂出去。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import uvicorn  # noqa: E402

from gaokao_audit import config, db  # noqa: E402
from gaokao_audit.api import guard as guard_mod  # noqa: E402
from gaokao_audit.api import main as api  # noqa: E402


def make_app():
    # 每请求现开一条（同步端点在线程池里跑）
    g = guard_mod.Guard(
        per_ip_daily=int(__import__("os").environ.get("PER_IP_DAILY", "3")),
        global_cap_yuan=float(__import__("os").environ.get("GLOBAL_CAP_YUAN", "10")),
    )
    return api.create_app(conn_factory=lambda: db.connect(config.DB_PATH), guard=g)


if __name__ == "__main__":
    # ⚠️ 默认只听本机（安全）。**容器里必须设 HOST=0.0.0.0**，否则宿主连不上 ——
    # 这个坑是"本地起来真访问"那一步抓出来的：日志显示 uvicorn 绑在 127.0.0.1，
    # 容器端口映射形同虚设。
    import os

    uvicorn.run(
        make_app(),
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
    )
