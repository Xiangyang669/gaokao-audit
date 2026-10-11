"""LLM 响应缓存。

**为什么缓存是这套设计的核心，而不只是省钱**：
模型输出是非确定性的。不缓存的话，测试会随机红绿、演示每次结果都不一样、
评测没法复现 —— 而我们整个项目的主张就是「**每个数字都能复现**」。

缓存文件**进仓库**：这样别人 clone 下来不配 key 也能跑通全部测试。
"""
import hashlib
import json
from pathlib import Path
from typing import Callable


def path_for(directory: Path, cache_key: str) -> Path:
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:16]
    return Path(directory) / f"{digest}.json"


def get_or_compute(directory: Path, cache_key: str, compute: Callable[[], str]) -> str:
    p = path_for(directory, cache_key)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))["content"]
    content = compute()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"cache_key": cache_key, "content": content}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return content
