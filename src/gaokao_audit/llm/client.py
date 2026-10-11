"""DeepSeek 调用封装：读 key、发请求、走缓存、解析结构化输出。

🔴 安全约定（spec §8.1）：
  - key **只从环境变量 / .env 读**，代码里永不出现字面量
  - **绝不**把 key 写进日志、异常消息、返回值。异常只带类型名。
  - `.env` 必须在 .gitignore 里（已加，且 git check-ignore 验证过）

⚠️ 模型名以**实测的可用列表**为准（`GET /models` 返回 `deepseek-flash` / `deepseek-v4-pro`），
不是凭记忆 —— 我第一版写的 `deepseek-chat` 在这个账号上**根本不存在**。
可用环境变量覆盖。
"""
import base64
import json
import os
import urllib.request
from pathlib import Path

from gaokao_audit.llm import cache

# ⚠️ parents[3] 才是项目根：client.py → llm → gaokao_audit → src → <root>
CACHE_DIR = Path(__file__).resolve().parents[3] / "llm_cache"
API_BASE = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
MODEL_TEXT = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
MODEL_VISION = os.environ.get("DEEPSEEK_VISION_MODEL", "deepseek-flash")
TIMEOUT_SECONDS = 120

_ROOT = Path(__file__).resolve().parents[3]


class MissingKey(RuntimeError):
    """缺少 API key。**刻意做成显式异常** —— 静默用空 key 会发一个注定失败的请求，
    然后被上层当成'模型不听话'，排查方向全错。"""


def _load_dotenv() -> None:
    """把项目根目录 .env 里的键值读进 os.environ（已存在的环境变量优先）。"""
    env = _ROOT / ".env"
    if not env.is_file():
        return
    for raw in env.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


def _api_key() -> str:
    _load_dotenv()
    key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not key:
        raise MissingKey(
            "缺少环境变量 DEEPSEEK_API_KEY —— 在项目根目录建一个 .env，"
            "写 DEEPSEEK_API_KEY=<你的 key>（.env 已在 .gitignore 里，不会被提交）"
        )
    return key


def _post(payload: dict) -> str:
    """真发一次请求。**异常消息里只带异常类型名** —— 绝不回显请求体或 key。"""
    key = _api_key()
    req = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"DeepSeek 请求失败（{type(exc).__name__}）") from None
    return body["choices"][0]["message"]["content"]


def _run(messages: list[dict], cache_key: str | None) -> str:
    key = cache_key or json.dumps(messages, ensure_ascii=False, sort_keys=True)
    return cache.get_or_compute(CACHE_DIR, key, lambda: _post(
        {"model": MODEL_TEXT, "messages": messages}
    ))


def chat(messages: list[dict], *, cache_key: str | None = None) -> str:
    return _run(messages, cache_key)


def vision(image_path: str | Path, prompt: str, *, cache_key: str | None = None) -> str:
    """把一张图连同提示词发过去。图片走 base64 内联（不走外链，避免依赖图床）。"""
    path = Path(image_path)
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    suffix = path.suffix.lstrip(".").lower() or "png"
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/{suffix};base64,{b64}"}},
            ],
        }
    ]
    key = cache_key or f"vision:{path.name}:{prompt}"
    return cache.get_or_compute(CACHE_DIR, key, lambda: _post(
        {"model": MODEL_VISION, "messages": messages}
    ))
