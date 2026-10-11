"""Task 1 · LLM 客户端 + 响应缓存.

**默认必须离线**：只有缓存没命中时才真的发请求。这条不只是为了省钱 ——
它让所有测试和演示**可复现**（同一输入永远给同一输出），不然 LLM 的非确定性会污染一切。
"""
import json
import pytest

from gaokao_audit.llm import client


@pytest.fixture
def offline(tmp_path, monkeypatch):
    """把缓存指向临时目录，并记下每一次"真的发了请求"。"""
    monkeypatch.setattr(client, "CACHE_DIR", tmp_path)
    calls = []
    monkeypatch.setattr(client, "_post", lambda payload: calls.append(payload) or '{"ok":1}')
    return calls


def test_second_call_hits_cache_and_does_not_post(offline):
    a = client.chat([{"role": "user", "content": "hi"}], cache_key="k1")
    b = client.chat([{"role": "user", "content": "hi"}], cache_key="k1")
    assert a == b
    assert len(offline) == 1, "第二次必须命中缓存，不能又发一次请求"


def test_different_cache_keys_do_post_again(offline):
    client.chat([{"role": "user", "content": "hi"}], cache_key="k1")
    client.chat([{"role": "user", "content": "hi"}], cache_key="k2")
    assert len(offline) == 2


def test_cache_file_is_written_under_cache_dir(offline, tmp_path):
    client.chat([{"role": "user", "content": "hi"}], cache_key="k1")
    assert list(tmp_path.glob("*.json")), "缓存没落盘 —— 重启后就得再花钱"


def test_missing_key_raises_clear_error(monkeypatch, tmp_path):
    """⚠️ 必须把 `_ROOT` 也指向一个**没有 .env** 的目录 ——
    否则真实项目里的 .env 会把 key 补回来，这个用例就永远测不到缺 key 的路径。"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(client, "_ROOT", tmp_path)
    monkeypatch.setattr(client, "CACHE_DIR", tmp_path)  # 也必须隔离缓存，否则会命中别的用例写下的条目
    with pytest.raises(client.MissingKey) as e:
        client.chat([{"role": "user", "content": "hi"}], cache_key="nope")
    assert "DEEPSEEK_API_KEY" in str(e.value), "报错要说清是哪个环境变量缺了"


def test_key_is_never_echoed_in_errors(monkeypatch, offline):
    """🔴 安全：异常里绝不能带出 key。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-SECRET-CANARY")

    def boom(payload):
        raise RuntimeError(f"请求失败，payload={json.dumps(payload)}")

    monkeypatch.setattr(client, "_post", boom)
    try:
        client.chat([{"role": "user", "content": "hi"}], cache_key="k9")
    except Exception as e:  # noqa: BLE001
        assert "sk-SECRET-CANARY" not in str(e), "key 从异常里漏出去了"


def test_cache_dir_is_at_project_root():
    """🔴 回归护栏：缓存目录一度落在 `src/llm_cache`（parents 索引算错），
    而且**被 git 跟踪了** —— 那是"凭记忆算相对路径"的经典翻车。
    这里用"同级有 pyproject.toml"来锚定项目根，比数 parents 更稳。"""
    assert client.CACHE_DIR.name == "llm_cache"
    assert (client.CACHE_DIR.parent / "pyproject.toml").is_file(), (
        f"缓存目录不在项目根：{client.CACHE_DIR}"
    )
