"""共享 fixture：一个灌好数据的只读 SQLite（整个 session 建一次）。"""
import pytest

from gaokao_audit import config, db


@pytest.fixture(scope="session")
def conn(tmp_path_factory):
    from scripts import build_db

    p = tmp_path_factory.mktemp("db") / "t.db"
    build_db.build(config.RAW_DIR, p)
    # 测试复用一条连接、而端点跑在线程池里 —— 这里必须显式放开线程检查。
    # 生产走的是 conn_factory（每请求现开），不需要这个开关。
    c = db.connect(p, check_same_thread=False)
    yield c
    c.close()
